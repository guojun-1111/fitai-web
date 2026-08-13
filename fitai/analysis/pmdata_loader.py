# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""V7.0 Research: PMData 公开数据集加载器。

PMData (Thambawita et al., MMSys 2020) 是挪威 Simula 实验室发布的
公开可穿戴健康数据集，包含 16 名参与者 5 个月的 Fitbit Versa 2 数据。

数据集地址: https://datasets.simula.no/pmdata/
HuggingFace 镜像: https://huggingface.co/datasets/aai530-group6/pmdata
许可证: CC BY-NC 4.0（科研免费使用）

数据结构:
  pXX/fitbit/heart_rate.json    — [{dateTime, value: {bpm, confidence}}]
  pXX/fitbit/steps.json         — [{dateTime, value}]
  pXX/fitbit/sleep.json         — [{dateOfSleep, levels: {summary: {light, deep, rem, wake}}}]
  pXX/fitbit/resting_heart_rate.json — [{dateTime, value}]
  pXX/googledocs/reporting.csv  — 每日自报（体重、饮水、饮食等）
  pXX/pmsys/srpe.csv            — session RPE 训练负荷
  pXX/pmsys/wellness.csv        — 每日自评（疲劳、心情、酸痛、压力、准备度）

用法:
    python -m fitai.analysis.pmdata_loader /path/to/pmdata/
"""
import json
import os
import math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


def load_pmdata_dataset(data_dir: str, participant_ids: list = None) -> list:
    """加载 PMData 数据集，转换为 fitai-web 评估格式。

    Args:
        data_dir: PMData 根目录（包含 p01, p02, ... 子目录）
        participant_ids: 要加载的参与者 ID 列表（如 ['01', '02']），默认全部

    Returns:
        list of dicts: [{"user_id": int, "data": {date: {metrics}}, "labels": {date: label}}]
    """
    data_root = Path(data_dir)
    if not data_root.exists():
        raise FileNotFoundError(f"PMData directory not found: {data_dir}")

    if participant_ids is None:
        participant_ids = sorted(
            d.name[1:] for d in data_root.iterdir()
            if d.is_dir() and d.name.startswith("p") and d.name[1:].isdigit()
        )

    datasets = []
    for pid in participant_ids:
        p_dir = data_root / f"p{pid}"
        if not p_dir.exists():
            continue

        ds = _load_participant(p_dir, int(pid))
        if ds and ds["data"]:
            datasets.append(ds)

    return datasets


def _load_participant(p_dir: Path, user_id: int) -> dict:
    """加载单个参与者的数据。"""
    fitbit_dir = p_dir / "fitbit"
    pmsys_dir = p_dir / "pmsys"
    gdocs_dir = p_dir / "googledocs"

    # ── 加载 Fitbit 数据 ──
    hr_data = _load_json(fitbit_dir / "heart_rate.json")
    steps_data = _load_json(fitbit_dir / "steps.json")
    sleep_data = _load_json(fitbit_dir / "sleep.json")
    rhr_data = _load_json(fitbit_dir / "resting_heart_rate.json")
    calories_data = _load_json(fitbit_dir / "calories.json")

    # ── 聚合为每日格式 ──
    daily = defaultdict(dict)

    # 心率（聚合为日均值）
    if hr_data:
        hr_daily = defaultdict(list)
        for entry in hr_data:
            dt_str = entry.get("dateTime", "")
            date = dt_str[:10] if dt_str else ""
            val = entry.get("value", {})
            if isinstance(val, dict):
                bpm = val.get("bpm", 0)
            else:
                bpm = val
            if bpm and date:
                try:
                    hr_daily[date].append(float(bpm))
                except (ValueError, TypeError):
                    pass
        for date, bpms in hr_daily.items():
            daily[date]["heart_rate"] = round(sum(bpms) / len(bpms), 1)

    # 步数
    if steps_data:
        steps_daily = defaultdict(int)
        for entry in steps_data:
            dt_str = entry.get("dateTime", "")
            date = dt_str[:10] if dt_str else ""
            val = entry.get("value", 0) or 0
            if date:
                try:
                    steps_daily[date] += int(float(val))
                except (ValueError, TypeError):
                    pass
        for date, s in steps_daily.items():
            daily[date]["steps"] = s

    # 睡眠（总分钟数）— PMData 格式: {light: {count, minutes}, deep: {count, minutes}, ...}
    if sleep_data:
        for entry in sleep_data:
            date = entry.get("dateOfSleep", "")
            summary = entry.get("levels", {}).get("summary", {})
            total_min = 0
            for stage in ("light", "deep", "rem"):
                stage_data = summary.get(stage, {})
                if isinstance(stage_data, dict):
                    total_min += int(stage_data.get("minutes", 0) or 0)
                else:
                    total_min += int(stage_data or 0)
            duration_ms = entry.get("duration", 0) or 0
            if total_min == 0 and duration_ms > 0:
                total_min = int(duration_ms / 60000)
            if date:
                daily[date]["sleep"] = total_min

    # 静息心率 — PMData 格式: {"dateTime":"...", "value":{"date":"...", "value":53.7, "error":6.8}}
    if rhr_data:
        for entry in rhr_data:
            dt_str = entry.get("dateTime", "")
            date = dt_str[:10] if dt_str else ""
            val = entry.get("value", {})
            if isinstance(val, dict):
                try:
                    rhr = float(val.get("value", 0))
                except (ValueError, TypeError):
                    rhr = 0
            else:
                try:
                    rhr = float(val or 0)
                except (ValueError, TypeError):
                    rhr = 0
            if rhr and date:
                daily[date]["resting_heart_rate"] = rhr

    # 卡路里（聚合为日总量）
    if calories_data:
        cal_daily = defaultdict(float)
        for entry in calories_data:
            dt_str = entry.get("dateTime", "")
            date = dt_str[:10] if dt_str else ""
            val = entry.get("value", 0) or 0
            if date:
                try:
                    cal_daily[date] += float(val)
                except (ValueError, TypeError):
                    pass
        for date, c in cal_daily.items():
            daily[date]["calories"] = round(c, 1)

    # ── 加载 sRPE 训练负荷 ──
    # sRPE CSV 格式: end_date_time, activity_names, perceived_exertion, duration_min
    srpe_daily = defaultdict(float)
    if pmsys_dir.exists():
        srpe_file = pmsys_dir / "srpe.csv"
        if srpe_file.exists():
            with open(srpe_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in lines[1:]:
                parts = line.strip().split(",")
                if len(parts) >= 4:
                    date = parts[0].strip()[:10]  # ISO → YYYY-MM-DD
                    try:
                        rpe = float(parts[2].strip()) if parts[2].strip() else 0
                        duration = float(parts[3].strip()) if parts[3].strip() else 0
                    except (ValueError, TypeError):
                        continue
                    srpe_daily[date] += rpe * duration

        # ── 加载自评恢复分数 ──
        # wellness CSV: effective_time_frame, fatigue, mood, readiness, ...
        # readiness 在索引 3 (0-based)
        wellness_file = pmsys_dir / "wellness.csv"
        wellness_labels = {}
        if wellness_file.exists():
            with open(wellness_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in lines[1:]:
                parts = line.strip().split(",")
                if len(parts) >= 4:
                    date = parts[0].strip()[:10]  # ISO → YYYY-MM-DD
                    try:
                        readiness = float(parts[3].strip())
                    except (ValueError, IndexError):
                        readiness = None
                    if readiness is not None:
                        wellness_labels[date] = readiness

    # ── 生成标签（基于 sRPE + 心率恢复）──
    labels = {}
    sorted_dates = sorted(daily.keys())
    for i, date in enumerate(sorted_dates):
        metrics = daily[date]
        hr = metrics.get("heart_rate", 65)
        rhr = metrics.get("resting_heart_rate", 60)
        srpe = srpe_daily.get(date, 0)

        # 过度训练标签生成
        if srpe > 500 and hr > rhr * 1.15:
            labels[date] = "overtraining"
        elif metrics.get("sleep", 480) < 300 and metrics.get("calories", 2500) < 1000:
            labels[date] = "under_recovery"
        elif srpe > 300 and metrics.get("steps", 8000) > 12000:
            labels[date] = "stress"
        elif metrics.get("sleep", 480) < 360 and metrics.get("calories", 2500) < 1000:
            labels[date] = "metabolic"
        else:
            labels[date] = "normal"

        # 添加 sRPE 到指标
        daily[date]["srpe"] = round(srpe, 1)
        if date in wellness_labels:
            daily[date]["wellness_readiness"] = wellness_labels[date]

    if not daily:
        return {"user_id": user_id, "data": {}, "labels": {}, "n_days": 0}

    return {
        "user_id": user_id,
        "data": dict(daily),
        "labels": labels,
        "n_days": len(daily),
        "date_range": [min(daily.keys()), max(daily.keys())],
    }


def _load_json(path: Path) -> list:
    """安全加载 JSON 文件。"""
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, IOError):
        return []


# ═══════════════════════════════════════════════════════════════════
# 用法示例
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m fitai.analysis.pmdata_loader /path/to/pmdata/")
        print()
        print("Download PMData from: https://datasets.simula.no/pmdata/")
        print("Or HuggingFace: https://huggingface.co/datasets/aai530-group6/pmdata")
        sys.exit(1)

    data_dir = sys.argv[1]
    datasets = load_pmdata_dataset(data_dir)

    print(f"Loaded {len(datasets)} participants")
    for ds in datasets[:3]:
        print(f"  User {ds['user_id']}: {ds['n_days']} days, "
              f"range={ds.get('date_range', ['?', '?'])}")
        anomaly_count = sum(1 for l in ds["labels"].values() if l != "normal")
        print(f"    Anomalies detected: {anomaly_count}")
