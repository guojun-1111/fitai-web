# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""Kaggle Fitbit 公开数据集加载器。

Kaggle Fitbit Fitness Tracker Data (Furberg et al., 2016)
是 Amazon Mechanical Turk 收集的 30 名 Fitbit 用户 2 个月数据。

来源: https://www.kaggle.com/datasets/arashnic/fitbit
许可证: CC0（公域，自由使用）

数据结构（31 天 × 2 批）:
  dailyActivity_merged.csv  — Id, ActivityDate, TotalSteps, Calories, ...
  heartrate_seconds_merged.csv — Id, Time, Value (5 秒间隔)
  minuteSleep_merged.csv   — Id, date, value (1=asleep, 2=restless, 3=awake)
  weightLogInfo_merged.csv — Id, Date, WeightKg, BMI, Fat

用法:
    python -m fitai.analysis.kaggle_loader data/fitbit/
"""
import csv
import os
from collections import defaultdict
from pathlib import Path


def load_kaggle_dataset(data_dir: str, min_days: int = 14) -> list:
    """加载 Kaggle Fitbit 数据集，转换为 fitai-web 评估格式。

    Args:
        data_dir: fitbit 数据根目录（含 mturkfitbit_export_* 子目录）
        min_days: 最少天数阈值，低于此阈值的参与者跳过

    Returns:
        list of dicts: [{"user_id": int, "data": {date: {metrics}}, "labels": {date: label}}]
    """
    data_root = Path(data_dir)
    if not data_root.exists():
        raise FileNotFoundError(f"Kaggle Fitbit directory not found: {data_dir}")

    # 发现数据子目录
    subdirs = sorted(
        d for d in data_root.iterdir()
        if d.is_dir() and d.name.startswith("mturkfitbit_export_")
    )

    if not subdirs:
        raise FileNotFoundError(f"No mturkfitbit_export_* directories in {data_dir}")

    # 合并多批数据（同一用户 ID 跨批次合并）
    user_daily = defaultdict(lambda: defaultdict(dict))
    user_hr = defaultdict(lambda: defaultdict(list))
    user_sleep = defaultdict(lambda: defaultdict(int))

    for subdir in subdirs:
        # 找到 Fitabase Data 子目录
        fitabase_dirs = list(subdir.glob("Fitabase Data *"))
        if not fitabase_dirs:
            continue
        fb_dir = fitabase_dirs[0]

        _load_daily_activity(fb_dir / "dailyActivity_merged.csv", user_daily)
        _load_heartrate(fb_dir / "heartrate_seconds_merged.csv", user_hr)
        _load_sleep(fb_dir / "minuteSleep_merged.csv", user_sleep)

    # 转换为标准格式
    datasets = []
    for user_id_str in sorted(user_daily.keys()):
        daily_data = dict(user_daily[user_id_str])
        if len(daily_data) < min_days:
            continue

        uid = int(user_id_str)

        # 聚合心率到日均值 + 静息心率
        for date, hr_list in user_hr[uid].items():
            if date in daily_data and hr_list:
                sorted_hr = sorted(hr_list)
                daily_data[date]["heart_rate"] = round(sum(hr_list) / len(hr_list), 1)
                # 静息心率 ≈ 最安静时段的均值的下 20% 分位数
                resting_candidates = sorted_hr[:max(1, len(sorted_hr) // 5)]
                daily_data[date]["resting_heart_rate"] = round(
                    sum(resting_candidates) / len(resting_candidates), 1
                )

        # 添加睡眠数据
        for date, sleep_min in user_sleep[uid].items():
            if date in daily_data:
                daily_data[date]["sleep"] = sleep_min

        # 生成标签
        labels = _generate_labels(daily_data)

        if not daily_data:
            continue

        sorted_dates = sorted(daily_data.keys())
        datasets.append({
            "user_id": uid,
            "data": daily_data,
            "labels": labels,
            "n_days": len(daily_data),
            "date_range": [sorted_dates[0], sorted_dates[-1]],
        })

    return datasets


def _load_daily_activity(csv_path: Path, user_daily: dict):
    """加载 dailyActivity_merged.csv → 每日指标。"""
    if not csv_path.exists():
        return
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            uid = row["Id"]
            date = row["ActivityDate"]
            try:
                steps = int(float(row.get("TotalSteps", 0) or 0))
                calories = float(row.get("Calories", 0) or 0)
                very_active_min = int(float(row.get("VeryActiveMinutes", 0) or 0))
                fairly_active_min = int(float(row.get("FairlyActiveMinutes", 0) or 0))
                lightly_active_min = int(float(row.get("LightlyActiveMinutes", 0) or 0))
                sedentary_min = int(float(row.get("SedentaryMinutes", 0) or 0))
            except (ValueError, TypeError):
                continue

            user_daily[uid][date].update({
                "steps": steps,
                "calories": round(calories, 1),
                "very_active_min": very_active_min,
                "fairly_active_min": fairly_active_min,
                "lightly_active_min": lightly_active_min,
                "sedentary_min": sedentary_min,
                "active_minutes": very_active_min + fairly_active_min + lightly_active_min,
                "srpe": _estimate_srpe(very_active_min, fairly_active_min),
            })


def _load_heartrate(csv_path: Path, user_hr: dict):
    """加载 heartrate_seconds_merged.csv → 逐日心率列表。"""
    if not csv_path.exists():
        return
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            uid = int(row["Id"])
            time_str = row["Time"]  # "4/1/2016 7:54:00 AM"
            try:
                hr = float(row["Value"])
            except (ValueError, TypeError):
                continue
            # 解析日期
            date = time_str.split()[0] if time_str else ""
            if date:
                user_hr[uid][date].append(hr)


def _load_sleep(csv_path: Path, user_sleep: dict):
    """加载 minuteSleep_merged.csv → 每日睡眠总分钟。value: 1=asleep, 2=restless, 3=awake"""
    if not csv_path.exists():
        return
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            uid = int(row["Id"])
            date_str = row.get("date", "")
            date = date_str.split()[0] if date_str else ""
            val = int(row.get("value", 0) or 0)
            if date and val in (1, 2):
                user_sleep[uid][date] += 1  # 每分钟一条记录


def _estimate_srpe(very_active_min: int, fairly_active_min: int) -> float:
    """从 Fitbit 活跃分钟数估算 sRPE 训练负荷。
    sRPE = RPE × duration(min)
    - Very active ≈ RPE 7-8
    - Fairly active ≈ RPE 4-5
    """
    return very_active_min * 7.5 + fairly_active_min * 4.5


def _generate_labels(daily_data: dict) -> dict:
    """从每日指标生成异常标签。使用与 PMData 类似的标准。"""
    labels = {}
    # 计算基线
    hr_values = [m.get("heart_rate", 65) for m in daily_data.values() if "heart_rate" in m]
    sleep_values = [m.get("sleep", 420) for m in daily_data.values() if "sleep" in m]
    cal_values = [m.get("calories", 2000) for m in daily_data.values() if "calories" in m]
    steps_values = [m.get("steps", 8000) for m in daily_data.values() if "steps" in m]

    avg_hr = sum(hr_values) / len(hr_values) if hr_values else 65
    avg_sleep = sum(sleep_values) / len(sleep_values) if sleep_values else 420
    avg_cal = sum(cal_values) / len(cal_values) if cal_values else 2000
    avg_steps = sum(steps_values) / len(steps_values) if steps_values else 8000

    for date, metrics in daily_data.items():
        hr = metrics.get("heart_rate", avg_hr)
        sleep_min = metrics.get("sleep", avg_sleep)
        calories = metrics.get("calories", avg_cal)
        steps = metrics.get("steps", avg_steps)

        if hr > avg_hr * 1.12 and sleep_min < avg_sleep * 0.7:
            labels[date] = "overtraining"
        elif sleep_min < avg_sleep * 0.6 and calories < avg_cal * 0.5:
            labels[date] = "under_recovery"
        elif steps > avg_steps * 1.5 and hr > avg_hr * 1.05:
            labels[date] = "stress"
        elif sleep_min < avg_sleep * 0.75 and calories < avg_cal * 0.6:
            labels[date] = "metabolic"
        else:
            labels[date] = "normal"

    return labels


# ═══════════════════════════════════════════════════════════════════
# 用法示例
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m fitai.analysis.kaggle_loader data/fitbit/")
        print()
        print("Dataset: Kaggle Fitbit Fitness Tracker Data")
        print("Source: https://www.kaggle.com/datasets/arashnic/fitbit")
        sys.exit(1)

    data_dir = sys.argv[1]
    datasets = load_kaggle_dataset(data_dir)

    print(f"Loaded {len(datasets)} participants")
    total_days = 0
    for ds in sorted(datasets, key=lambda x: x["n_days"], reverse=True):
        total_days += ds["n_days"]
        anomaly_count = sum(1 for l in ds["labels"].values() if l != "normal")
        print(f"  User {ds['user_id']}: {ds['n_days']} days, "
              f"range={ds.get('date_range', ['?', '?'])}, "
              f"anomalies={anomaly_count}")
    print(f"Total: {len(datasets)} users, {total_days} days")
