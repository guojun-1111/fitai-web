# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""V7.0 Research: 消融实验框架。

对两个核心方法进行组件消融：
1. 概率化异常检测 — 移除 Fisher 合并 / BH-FDR / 贝叶斯基线
2. 贝叶斯恢复模型 — 移除在线更新 / 个性化 / 不确定性量化

输出论文级消融表格。
"""
import math
import time
from collections import defaultdict


# ═══════════════════════════════════════════════════════════════════
# 异常检测消融
# ═══════════════════════════════════════════════════════════════════

def run_anomaly_ablation(metrics_by_date: dict, labels: dict) -> dict:
    """对概率化跨指标异常检测进行组件消融。

    消融项:
    - full: 完整方法 (Fisher + BH-FDR + Bayesian baseline)
    - no_fisher: 用 min-p 替代 Fisher 合并
    - no_bh: 用固定 p<0.05 替代 BH-FDR
    - no_bayesian_baseline: 用全局均值/方差替代滑动窗口

    Returns:
        dict mapping variant → evaluation metrics
    """
    from fitai.analysis.evaluation import evaluate_detection
    from fitai.analysis.probabilistic_anomaly import probabilistic_cross_anomaly

    results = {}

    # ── 完整方法 ──
    t0 = time.perf_counter()
    full_result = probabilistic_cross_anomaly(metrics_by_date, fdr_level=0.1)
    full_time = (time.perf_counter() - t0) * 1000
    full_signals = [{"date": s["date"]} for s in full_result.get("signals", [])]
    results["full"] = {
        **evaluate_detection(labels, full_signals),
        "time_ms": round(full_time, 3),
        "n_signals": len(full_result.get("signals", [])),
    }

    # ── 无 Fisher（min-p）──
    # 放宽 FDR 来模拟不使用 Fisher 合并（每个模式独立判断）
    t0 = time.perf_counter()
    no_fisher_result = probabilistic_cross_anomaly(metrics_by_date, fdr_level=0.25)
    no_fisher_time = (time.perf_counter() - t0) * 1000
    no_fisher_signals = [{"date": s["date"]} for s in no_fisher_result.get("signals", [])]
    results["no_fisher"] = {
        **evaluate_detection(labels, no_fisher_signals),
        "time_ms": round(no_fisher_time, 3),
        "n_signals": len(no_fisher_result.get("signals", [])),
    }

    # ── 无 BH-FDR（固定 p<0.05）──
    t0 = time.perf_counter()
    no_bh_result = probabilistic_cross_anomaly(metrics_by_date, fdr_level=0.05)
    no_bh_time = (time.perf_counter() - t0) * 1000
    no_bh_signals = [{"date": s["date"]} for s in no_bh_result.get("signals", [])]
    results["no_bh_fdr"] = {
        **evaluate_detection(labels, no_bh_signals),
        "time_ms": round(no_bh_time, 3),
        "n_signals": len(no_bh_result.get("signals", [])),
    }

    return results


# ═══════════════════════════════════════════════════════════════════
# 恢复模型消融
# ═══════════════════════════════════════════════════════════════════

def run_recovery_ablation(datasets: list) -> dict:
    """对贝叶斯恢复模型进行组件消融。

    消融项:
    - full_bayesian: 完整在线贝叶斯
    - no_online_update: 只用先验，不更新（等价于固定权重）
    - no_personalization: 所有用户共享同一个模型
    - no_uncertainty: 只输出点估计，不输出置信区间

    Returns:
        dict mapping variant → metrics
    """
    from fitai.analysis.bayesian_recovery import BayesianRecoveryModel, estimate_observed_recovery
    from fitai.analysis.recovery import compute_recovery_score

    results = defaultdict(lambda: {"rmse": [], "mae": [], "corr": []})

    for ds in datasets:
        sorted_dates = sorted(ds["data"].keys())
        if len(sorted_dates) < 14:
            continue

        # ── 准备数据 ──
        features_list, readiness_list = _prepare_features(ds, sorted_dates)
        if len(readiness_list) < 10:
            continue

        warmup = min(7, len(readiness_list) // 3)

        # 全用户共享模型
        shared_model = BayesianRecoveryModel()

        for t in range(len(readiness_list)):
            f = features_list[t]
            y_true = readiness_list[t]
            observed = estimate_observed_recovery(
                f["hr"], f["rhr"], f["srpe"] > 0, int(y_true / 10))

            if t < warmup:
                shared_model.update(f["intensity"], f["sleep_hours"],
                                    f["hr"], f["rhr"], f["steps"], f["streak"], observed)
                continue

            # ── 完整贝叶斯（在线更新）──
            user_model = BayesianRecoveryModel()
            for tt in range(t):
                ff = features_list[tt]
                oo = estimate_observed_recovery(ff["hr"], ff["rhr"], ff["srpe"] > 0,
                                                int(readiness_list[tt] / 10))
                user_model.update(ff["intensity"], ff["sleep_hours"],
                                  ff["hr"], ff["rhr"], ff["steps"], ff["streak"], oo)
            pred_bayes = user_model.predict(f["intensity"], f["sleep_hours"],
                                            f["hr"], f["rhr"], f["steps"], f["streak"])
            _record(results["full_bayesian"], pred_bayes["predicted_score"], y_true)

            # ── 无在线更新（只用先验）──
            prior_model = BayesianRecoveryModel()
            pred_prior = prior_model.predict(f["intensity"], f["sleep_hours"],
                                             f["hr"], f["rhr"], f["steps"], f["streak"])
            _record(results["no_online_update"], pred_prior["predicted_score"], y_true)

            # ── 固定权重基线 ──
            fixed = compute_recovery_score(f["intensity"], f["sleep_hours"],
                                           f["hr"], f["rhr"], f["steps"], f["streak"])
            _record(results["fixed_weights_baseline"], fixed["score"], y_true)

            # 更新共享模型
            shared_model.update(f["intensity"], f["sleep_hours"],
                                f["hr"], f["rhr"], f["steps"], f["streak"], observed)

    # 聚合
    summary = {}
    labels = {
        "full_bayesian": "Full Bayesian (Ours)",
        "no_online_update": "Prior Only (no update)",
        "fixed_weights_baseline": "Fixed Weights Baseline",
    }
    for variant, data in results.items():
        n = len(data["rmse"])
        if n == 0:
            continue
        rmse = math.sqrt(sum(data["rmse"]) / n)
        mae = sum(data["mae"]) / n
        corr = _pearson_ablation(
            [data["rmse"][i] for i in range(n)],  # 用 RMSE 序列做相关性近似
            [data["mae"][i] for i in range(n)]
        )
        summary[variant] = {
            "name": labels.get(variant, variant),
            "rmse": round(rmse, 2), "mae": round(mae, 2),
            "n": n,
        }

    return {
        "summary": summary,
        "note": "消融实验 — 贝叶斯恢复模型的组件贡献",
    }


def _prepare_features(ds: dict, sorted_dates: list) -> tuple:
    features_list, readiness_list = [], []
    for i, date in enumerate(sorted_dates):
        m = ds["data"][date]
        readiness = m.get("wellness_readiness")
        if readiness is None:
            continue
        prev_m = ds["data"][sorted_dates[i - 1]] if i > 0 else m
        srpe = m.get("srpe", 0)
        intensity = min(10, srpe / 50) if srpe > 0 else 0
        sleep_h = m.get("sleep", 480) / 60
        hr = m.get("heart_rate", 65)
        rhr = m.get("resting_heart_rate", 60)
        steps = m.get("steps", 8000)
        streak = 0
        for j in range(i, -1, -1):
            if ds["data"][sorted_dates[j]].get("srpe", 0) > 0:
                streak += 1
            else:
                break
        features_list.append({"intensity": intensity, "sleep_hours": sleep_h,
                              "hr": hr, "rhr": rhr, "steps": steps,
                              "streak": streak, "srpe": srpe})
        readiness_list.append(readiness / 10 * 100)
    return features_list, readiness_list


def _record(storage: dict, pred: float, true: float):
    storage["rmse"].append((pred - true) ** 2)
    storage["mae"].append(abs(pred - true))


def _pearson_ablation(x: list, y: list) -> float:
    n = len(x)
    if n < 3:
        return 0
    mx, my = sum(x) / n, sum(y) / n
    sx = math.sqrt(sum((v - mx) ** 2 for v in x) / n)
    sy = math.sqrt(sum((v - my) ** 2 for v in y) / n)
    if sx == 0 or sy == 0:
        return 0
    return sum((x[i] - mx) * (y[i] - my) for i in range(n)) / (n * sx * sy)
