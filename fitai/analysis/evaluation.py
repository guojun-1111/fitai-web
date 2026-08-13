# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""V7.0 Research: 健康异常检测算法评估框架。

提供合成数据生成、基线方法对比和标准评估指标，
用于学术论文中的方法验证。

参考：
- Lavin & Ahmad, 2015. "Evaluating Real-Time Anomaly Detection"
- NAB benchmark methodology (Ahmad et al., 2017)
"""
import math
import random
from collections import defaultdict
from datetime import datetime, timedelta


# ═══════════════════════════════════════════════════════════════════
# 合成数据生成器
# ═══════════════════════════════════════════════════════════════════

def generate_synthetic_health_data(n_days: int = 60, n_users: int = 1,
                                    anomaly_rate: float = 0.05,
                                    seed: int = 42) -> list:
    """生成带标注的合成健康数据。

    模拟真实可穿戴数据特征：
    - 周周期性（步数周末多、睡眠周末补觉）
    - 个体差异性（每人基线不同）
    - 测量噪声（高斯噪声）
    - 可控异常注入（4 种风险模式，带 ground truth 标签）

    Args:
        n_days: 每个用户的天数
        n_users: 用户数量
        anomaly_rate: 异常天比例
        seed: 随机种子

    Returns:
        list of dicts: [{"user_id": 1, "data": {date: {metrics}}, "labels": {date: label}}]
    """
    rng = random.Random(seed)
    datasets = []

    for uid in range(1, n_users + 1):
        # 个性化基线
        baseline = {
            "steps": rng.uniform(6000, 12000),
            "sleep": rng.uniform(400, 520),
            "heart_rate": rng.uniform(58, 75),
            "calories": rng.uniform(2500, 3500),
            "weight": rng.uniform(55, 90),
        }
        weekly_amplitude = {
            "steps": rng.uniform(1000, 3000),
            "sleep": rng.uniform(30, 90),
        }
        noise_std = {
            "steps": rng.uniform(500, 1500),
            "sleep": rng.uniform(15, 45),
            "heart_rate": rng.uniform(2, 5),
            "calories": rng.uniform(200, 500),
            "weight": rng.uniform(0.1, 0.3),
        }

        data = {}
        labels = {}
        anomaly_dates = set()

        # 决定哪些天是异常天
        candidate_dates = list(range(n_days))
        rng.shuffle(candidate_dates)
        n_anomalies = max(1, int(n_days * anomaly_rate))
        for idx in candidate_dates[:n_anomalies]:
            anomaly_dates.add(idx)

        for day in range(n_days):
            date = (datetime(2026, 1, 1) + timedelta(days=day)).strftime("%Y-%m-%d")
            dow = day % 7  # 0=Mon, 5=Sat, 6=Sun

            # 基础值（加周周期性）
            steps_base = baseline["steps"]
            sleep_base = baseline["sleep"]
            if dow >= 5:  # 周末
                steps_base += weekly_amplitude["steps"]
                sleep_base += weekly_amplitude["sleep"]

            metrics = {
                "steps": max(0, steps_base + rng.gauss(0, noise_std["steps"])),
                "sleep": max(0, sleep_base + rng.gauss(0, noise_std["sleep"])),
                "heart_rate": max(40, baseline["heart_rate"] + rng.gauss(0, noise_std["heart_rate"])),
                "calories": max(0, baseline["calories"] + rng.gauss(0, noise_std["calories"])),
                "weight": baseline["weight"] + rng.gauss(0, noise_std["weight"]),
            }

            # 注入异常
            label = "normal"
            if day in anomaly_dates:
                anomaly_type = rng.choice(["overtraining", "metabolic", "stress", "under_recovery"])
                label = anomaly_type

                if anomaly_type == "overtraining":
                    metrics["sleep"] *= rng.uniform(0.5, 0.75)
                    metrics["heart_rate"] *= rng.uniform(1.15, 1.30)
                    metrics["steps"] *= rng.uniform(0.4, 0.6)
                elif anomaly_type == "metabolic":
                    metrics["calories"] *= rng.uniform(0.5, 0.7)
                    metrics["weight"] *= rng.uniform(1.02, 1.05)
                elif anomaly_type == "stress":
                    metrics["sleep"] *= rng.uniform(0.55, 0.75)
                    metrics["steps"] *= rng.uniform(1.3, 1.6)
                elif anomaly_type == "under_recovery":
                    metrics["sleep"] *= rng.uniform(0.5, 0.7)
                    metrics["calories"] *= rng.uniform(0.4, 0.6)

            data[date] = {k: round(v, 1) for k, v in metrics.items()}
            labels[date] = label

        datasets.append({
            "user_id": uid,
            "baseline": baseline,
            "data": data,
            "labels": labels,
            "n_anomalies": len(anomaly_dates),
            "anomaly_rate": anomaly_rate,
        })

    return datasets


# ═══════════════════════════════════════════════════════════════════
# 基线方法
# ═══════════════════════════════════════════════════════════════════

def baseline_zscore(metrics_by_date: dict, threshold: float = 2.5) -> list:
    """基线 1: 单指标 Z-score 异常检测。

    对每个指标独立计算 z-score，任一指标超过阈值即标记为异常。
    这是可穿戴设备中最常用的方法（Apple Health, Fitbit）。
    """
    dates = sorted(metrics_by_date.keys())
    n = len(dates)
    if n < 7:
        return []

    anomalies = []
    for date in dates[-14:]:
        today = metrics_by_date.get(date, {})
        for metric in ["steps", "sleep", "heart_rate", "calories", "weight"]:
            val = today.get(metric)
            if val is None or val <= 0:
                continue

            # 计算基线均值和标准差
            all_vals = []
            for d in dates:
                v = metrics_by_date.get(d, {}).get(metric)
                if v and v > 0:
                    all_vals.append(v)
            if len(all_vals) < 7:
                continue
            mean_v = sum(all_vals) / len(all_vals)
            var_v = sum((v - mean_v) ** 2 for v in all_vals) / len(all_vals)
            std_v = math.sqrt(var_v) if var_v > 0 else 1
            z = abs((val - mean_v) / std_v)
            if z > threshold:
                anomalies.append({
                    "date": date, "metric": metric, "z_score": round(z, 2),
                    "method": "zscore",
                })

    return anomalies


def baseline_ewma(metrics_by_date: dict, threshold: float = 2.0, half_life: int = 7) -> list:
    """基线 2: EWMA 残差异常检测。

    对每个指标计算指数加权移动平均，检测残差超过阈值的点。
    与我们的 ewma_health_score 共享 EWMA 思想，但作为单指标基线。
    """
    dates = sorted(metrics_by_date.keys())
    n = len(dates)
    if n < 7:
        return []

    decay = 0.5 ** (1.0 / half_life)
    anomalies = []

    for metric in ["steps", "sleep", "heart_rate", "calories", "weight"]:
        ewma = None
        ewma_var = None

        for date in dates:
            val = metrics_by_date.get(date, {}).get(metric)
            if val is None or val <= 0:
                continue

            if ewma is None:
                ewma = val
                ewma_var = 1.0
                continue

            # EWMA 更新
            ewma = decay * ewma + (1 - decay) * val
            residual = val - ewma
            ewma_var = decay * ewma_var + (1 - decay) * residual ** 2

            if ewma_var > 0:
                z = abs(residual) / math.sqrt(ewma_var)
                if z > threshold:
                    anomalies.append({
                        "date": date, "metric": metric, "z_score": round(z, 2),
                        "method": "ewma",
                    })

    return anomalies


# ═══════════════════════════════════════════════════════════════════
# 评估指标
# ═══════════════════════════════════════════════════════════════════

def evaluate_detection(ground_truth: dict, predicted_signals: list,
                        tolerance_days: int = 0) -> dict:
    """评估异常检测性能。

    Args:
        ground_truth: {date: label} — label 为 "normal" 或异常类型
        predicted_signals: [{"date": str, ...}, ...] — 检测到的异常
        tolerance_days: 容差天数（0 = 精确匹配，1 = ±1 天视为命中）

    Returns:
        dict with precision, recall, f1, confusion_matrix, detection_rate_by_type
    """
    true_anomaly_dates = {d for d, label in ground_truth.items() if label != "normal"}
    pred_dates = set()

    for s in predicted_signals:
        pred_date = s.get("date", "")
        if tolerance_days > 0:
            from datetime import datetime, timedelta
            dt = datetime.strptime(pred_date, "%Y-%m-%d")
            for offset in range(-tolerance_days, tolerance_days + 1):
                adj = (dt + timedelta(days=offset)).strftime("%Y-%m-%d")
                if adj in true_anomaly_dates:
                    pred_dates.add(adj)
        else:
            pred_dates.add(pred_date)

    tp = len(pred_dates & true_anomaly_dates)
    fp = len(pred_dates - true_anomaly_dates)
    fn = len(true_anomaly_dates - pred_dates)

    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-10)

    # 按异常类型统计
    by_type = defaultdict(lambda: {"total": 0, "detected": 0})
    for date, label in ground_truth.items():
        if label != "normal":
            by_type[label]["total"] += 1
    for s in predicted_signals:
        s_date = s.get("date", "")
        if s_date in ground_truth and ground_truth[s_date] != "normal":
            by_type[ground_truth[s_date]]["detected"] += 1

    detection_rates = {}
    for atype, counts in by_type.items():
        detection_rates[atype] = {
            "total": counts["total"],
            "detected": counts["detected"],
            "rate": round(counts["detected"] / max(counts["total"], 1), 3),
        }

    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1_score": round(f1, 3),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "n_true_anomalies": len(true_anomaly_dates),
        "n_predicted": len(predicted_signals),
        "detection_by_type": detection_rates,
    }


def compare_methods(dataset: dict) -> dict:
    """在一份合成数据上对比所有方法。

    Returns:
        dict mapping method_name -> evaluation metrics
    """
    results = {}

    # 方法 1: 概率化跨指标检测（我们的方法）
    from fitai.analysis.probabilistic_anomaly import probabilistic_cross_anomaly
    prob_result = probabilistic_cross_anomaly(dataset["data"])
    prob_signals = prob_result.get("signals", [])
    results["probabilistic_cross_metric"] = evaluate_detection(
        dataset["labels"], prob_signals)

    # 基线 1: Z-score
    zscore_signals = baseline_zscore(dataset["data"])
    results["zscore_baseline"] = evaluate_detection(
        dataset["labels"], zscore_signals)

    # 基线 2: EWMA
    ewma_signals = baseline_ewma(dataset["data"])
    results["ewma_baseline"] = evaluate_detection(
        dataset["labels"], ewma_signals)

    # 基线 3: 原始硬编码阈值方法
    from fitai.analysis.advanced import cross_metric_anomaly
    original_signals = cross_metric_anomaly(dataset["data"])
    original_formatted = [{"date": s["date"]} for s in original_signals]
    results["original_threshold"] = evaluate_detection(
        dataset["labels"], original_formatted)

    return results


# ═══════════════════════════════════════════════════════════════════
# 校准评估
# ═══════════════════════════════════════════════════════════════════

def evaluate_calibration(predicted_scores: list, observed_outcomes: list,
                          n_bins: int = 10) -> dict:
    """评估概率预测的校准度。

    将预测分数分箱，比较每箱的预测概率 vs 实际频率。
    输出可靠性图和期望校准误差（ECE）。

    Args:
        predicted_scores: list of predicted probabilities [0, 1]
        observed_outcomes: list of binary outcomes {0, 1}
        n_bins: 分箱数

    Returns:
        dict with ece, mce, bin_stats, reliability_data
    """
    if len(predicted_scores) != len(observed_outcomes) or len(predicted_scores) == 0:
        return {"ece": None, "error": "数据不足"}

    pairs = list(zip(predicted_scores, observed_outcomes))
    pairs.sort(key=lambda x: x[0])

    n = len(pairs)
    bin_size = n // n_bins
    if bin_size < 1:
        bin_size = 1
        n_bins = n

    bin_stats = []
    ece_sum = 0.0
    total_weight = 0.0

    for i in range(n_bins):
        start = i * bin_size
        end = n if i == n_bins - 1 else (i + 1) * bin_size
        bin_pairs = pairs[start:end]
        if not bin_pairs:
            continue

        bin_count = len(bin_pairs)
        avg_pred = sum(p[0] for p in bin_pairs) / bin_count
        actual_freq = sum(p[1] for p in bin_pairs) / bin_count

        weight = bin_count / n
        ece_sum += weight * abs(avg_pred - actual_freq)
        total_weight += weight

        bin_stats.append({
            "bin": i + 1,
            "count": bin_count,
            "avg_predicted": round(avg_pred, 3),
            "actual_frequency": round(actual_freq, 3),
            "gap": round(abs(avg_pred - actual_freq), 3),
        })

    ece = ece_sum / max(total_weight, 1e-10)
    mce = max((abs(s["avg_predicted"] - s["actual_frequency"]) for s in bin_stats), default=0)

    return {
        "ece": round(ece, 4),
        "mce": round(mce, 4),
        "n_samples": n,
        "n_bins": n_bins,
        "bin_stats": bin_stats,
        "interpretation": ("校准良好" if ece < 0.05 else
                           "校准一般" if ece < 0.1 else
                           "校准较差，需重新校准"),
    }
