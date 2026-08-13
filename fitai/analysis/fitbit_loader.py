# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""V7.0 Research: Kaggle Fitbit 数据集加载器。

Fitbit Fitness Tracker Data (Kaggle, CC0 公共领域):
  30 名 Fitbit 用户, 2016-03-12 ~ 2016-05-12 (2 个月)
  URL: https://www.kaggle.com/datasets/arashnic/fitbit
  文件: dailyActivity_merged.csv, sleepDay_merged.csv, heartrate_seconds_merged.csv, weightLogInfo_merged.csv

数据集结构:
  dailyActivity_merged.csv:
    Id, ActivityDate, TotalSteps, TotalDistance, TrackerDistance,
    LoggedActivitiesDistance, VeryActiveDistance, ModeratelyActiveDistance,
    LightActiveDistance, SedentaryActiveDistance, VeryActiveMinutes,
    FairlyActiveMinutes, LightlyActiveMinutes, SedentaryMinutes, Calories

  sleepDay_merged.csv:
    Id, SleepDay, TotalSleepRecords, TotalMinutesAsleep, TotalTimeInBed

  heartrate_seconds_merged.csv (极大数据量):
    Id, Time, Value

  weightLogInfo_merged.csv:
    Id, Date, WeightKg, WeightPounds, Fat, BMI, IsManualReport, LogId

用法:
    python -m fitai.analysis.fitbit_loader /path/to/fitbit_csvs/
"""
import csv
import os
from collections import defaultdict
from pathlib import Path


def _find_csv(data_root: Path, filename: str) -> Path:
    """在目录树中递归查找 CSV 文件（处理 Kaggle 解压后的嵌套结构）。"""
    matches = list(data_root.rglob(filename))
    return matches[0] if matches else data_root / filename


def load_fitbit_dataset(data_dir: str) -> list:
    """加载 Kaggle Fitbit 数据集。

    自动发现目录树中的所有 CSV 文件（支持嵌套子目录）。

    Args:
        data_dir: 包含 CSV 文件的目录（可含子目录）

    Returns:
        list of {"user_id": int, "data": {date: {metrics}}, "labels": {date: label}}
    """
    data_root = Path(data_dir)
    if not data_root.exists():
        raise FileNotFoundError(f"Directory not found: {data_dir}")

    # 加载所有 CSV（自动在子目录中查找）
    daily_activity = _read_csv(_find_csv(data_root, "dailyActivity_merged.csv"))
    sleep_data = _read_csv(_find_csv(data_root, "sleepDay_merged.csv"))
    weight_data = _read_csv(_find_csv(data_root, "weightLogInfo_merged.csv"))

    # HR 数据是可选的（文件极大）
    hr_data = _read_csv(_find_csv(data_root, "heartrate_seconds_merged.csv"))

    # ── 按用户分组 ──
    users = set()
    for row in daily_activity:
        uid = row.get("Id", "")
        if uid:
            users.add(uid)

    datasets = []
    for uid in sorted(users)[:10]:  # 前 10 个用户（样本充足）
        daily = defaultdict(dict)

        # 步数 + 卡路里
        for row in daily_activity:
            if row.get("Id") != uid:
                continue
            date = row.get("ActivityDate", "")
            if not date:
                continue
            daily[date]["steps"] = int(float(row.get("TotalSteps", 0) or 0))
            daily[date]["calories"] = int(float(row.get("Calories", 0) or 0))

        # 睡眠
        for row in sleep_data:
            if row.get("Id") != uid:
                continue
            date_time = row.get("SleepDay", "")
            date = date_time.split()[0] if date_time else ""
            if not date:
                continue
            daily[date]["sleep"] = int(float(row.get("TotalMinutesAsleep", 0) or 0))

        # 体重
        for row in weight_data:
            if row.get("Id") != uid:
                continue
            date_time = row.get("Date", "")
            date = date_time.split()[0] if date_time else ""
            if not date:
                continue
            wt = float(row.get("WeightKg", 0) or 0)
            if wt > 0:
                daily[date]["weight"] = round(wt, 1)

        # 心率 — 聚合为日平均
        if hr_data:
            hr_daily = defaultdict(list)
            for row in hr_data:
                if row.get("Id") != uid:
                    continue
                date_time = row.get("Time", "")
                date = date_time.split()[0] if date_time else ""
                val = row.get("Value", 0) or 0
                if date and float(val) > 0:
                    hr_daily[date].append(float(val))
            for date, vals in hr_daily.items():
                daily[date]["heart_rate"] = round(sum(vals) / len(vals), 1)

        if not daily:
            continue

        datasets.append({
            "user_id": int(uid),
            "data": dict(daily),
            "labels": {d: "normal" for d in daily},
            "n_days": len(daily),
            "source": "Kaggle Fitbit (CC0)",
        })

    return datasets


def _read_csv(path: Path) -> list:
    """读取 CSV 文件，返回字典列表。"""
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m fitai.analysis.fitbit_loader /path/to/fitbit_csvs/")
        print("Download from: https://www.kaggle.com/datasets/arashnic/fitbit")
        sys.exit(1)

    datasets = load_fitbit_dataset(sys.argv[1])
    print(f"Loaded {len(datasets)} users")
    for ds in datasets:
        print(f"  User {ds['user_id']}: {ds['n_days']} days")
