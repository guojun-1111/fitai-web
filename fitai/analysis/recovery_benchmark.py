# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""V7.0 Research: 恢复评分基准评估 — PMData 真实数据。

用 PMData 的 wellness readiness 自评（1-10）作为 ground truth，
对比贝叶斯个性化恢复模型 vs 固定权重基线 vs Whoop/Oura 风格模型。

叙事: "Personalized Recovery Scoring from Consumer Wearable Data:
        An Online Bayesian Approach for Edge Devices"
"""
import math
import time
import random
from collections import defaultdict
from datetime import datetime, timedelta


def run_recovery_benchmark(data_dir: str) -> dict:
    """在 PMData 上评估恢复评分模型。

    使用 wellness.csv 中的 readiness (1-10) 作为 ground truth,
    对比 3 种恢复评分方法。

    Returns:
        dict with per_method rmse, mae, correlation, calibration
    """
    from fitai.analysis.pmdata_loader import load_pmdata_dataset
    from fitai.analysis.bayesian_recovery import BayesianRecoveryModel, estimate_observed_recovery
    from fitai.analysis.recovery import compute_recovery_score
    from fitai.analysis.evaluation import evaluate_calibration

    datasets = load_pmdata_dataset(data_dir)
    if not datasets:
        return {"error": "No data loaded"}

    results = {
        "bayesian_online": {"rmse": [], "mae": [], "pred_scores": [], "true_scores": [],
                            "calib_preds": [], "calib_outs": []},
        "fixed_weights": {"rmse": [], "mae": [], "pred_scores": [], "true_scores": [],
                          "calib_preds": [], "calib_outs": []},
        "whoop_style": {"rmse": [], "mae": [], "pred_scores": [], "true_scores": [],
                        "calib_preds": [], "calib_outs": []},
    }

    for ds in datasets:
        model = BayesianRecoveryModel()
        sorted_dates = sorted(ds["data"].keys())
        if len(sorted_dates) < 14:
            continue

        # 收集时序数据：按日期对齐 metrics 和 readiness
        features_list = []
        readiness_list = []

        for date in sorted_dates:
            m = ds["data"][date]
            # 需要前一天的训练数据来计算强度
            prev_date_idx = sorted_dates.index(date)
            prev_m = ds["data"][sorted_dates[prev_date_idx - 1]] if prev_date_idx > 0 else m

            # 特征提取
            workout_intensity = 0
            srpe = m.get("srpe", 0)
            if srpe > 0:
                workout_intensity = min(10, srpe / 50)

            sleep_hours = m.get("sleep", 480) / 60  # 分钟 → 小时
            hr = m.get("heart_rate", 65)
            rhr = m.get("resting_heart_rate", 60)
            steps = m.get("steps", 8000)

            # 连续训练天数（简化：检查前一天的 sRPE）
            streak = 0
            for i in range(prev_date_idx, -1, -1):
                if ds["data"][sorted_dates[i]].get("srpe", 0) > 0:
                    streak += 1
                else:
                    break

            # Ground truth: wellness readiness (1-10) → 映射到 0-100
            readiness = m.get("wellness_readiness")
            if readiness is None:
                continue
            recovery_true = readiness / 10 * 100  # 1-10 → 0-100

            features_list.append({
                "intensity": workout_intensity,
                "sleep_hours": sleep_hours,
                "hr": hr,
                "rhr": rhr,
                "steps": steps,
                "streak": streak,
                "srpe": srpe,
            })
            readiness_list.append(recovery_true)

        if len(readiness_list) < 10:
            continue

        # ── 滚动评估：前 7 天作为训练，之后逐天预测 ──
        warmup = min(7, len(readiness_list) // 3)
        model = BayesianRecoveryModel()

        for t in range(len(readiness_list)):
            f = features_list[t]
            y_true = readiness_list[t]

            if t < warmup:
                # 训练阶段
                observed = estimate_observed_recovery(
                    f["hr"], f["rhr"], f["srpe"] > 0,
                    self_reported_feeling=int(readiness_list[t] / 10))
                model.update(f["intensity"], f["sleep_hours"],
                             f["hr"], f["rhr"], f["steps"], f["streak"],
                             observed)
                continue

            # 预测
            pred_bayes = model.predict(f["intensity"], f["sleep_hours"],
                                       f["hr"], f["rhr"], f["steps"], f["streak"])
            bayes_score = pred_bayes["predicted_score"]

            # 基线 1: 固定权重
            fixed = compute_recovery_score(
                f["intensity"], f["sleep_hours"], f["hr"], f["rhr"],
                f["steps"], f["streak"])
            fixed_score = fixed["score"]

            # 基线 2: Whoop 风格（简化为 sleep + HR 加权）
            whoop_score = (f["sleep_hours"] / 8 * 40 +
                           (1 - max(0, f["hr"] - f["rhr"]) / 20) * 30 +
                           min(f["steps"] / 10000, 1) * 20 + 10)
            whoop_score = max(0, min(100, whoop_score))

            # 记录
            results["bayesian_online"]["rmse"].append((bayes_score - y_true) ** 2)
            results["bayesian_online"]["mae"].append(abs(bayes_score - y_true))
            results["bayesian_online"]["pred_scores"].append(bayes_score)
            results["bayesian_online"]["true_scores"].append(y_true)
            results["bayesian_online"]["calib_preds"].append(bayes_score / 100)
            results["bayesian_online"]["calib_outs"].append(1 if y_true >= 70 else 0)

            results["fixed_weights"]["rmse"].append((fixed_score - y_true) ** 2)
            results["fixed_weights"]["mae"].append(abs(fixed_score - y_true))
            results["fixed_weights"]["pred_scores"].append(fixed_score)
            results["fixed_weights"]["true_scores"].append(y_true)
            results["fixed_weights"]["calib_preds"].append(fixed_score / 100)
            results["fixed_weights"]["calib_outs"].append(1 if y_true >= 70 else 0)

            results["whoop_style"]["rmse"].append((whoop_score - y_true) ** 2)
            results["whoop_style"]["mae"].append(abs(whoop_score - y_true))
            results["whoop_style"]["pred_scores"].append(whoop_score)
            results["whoop_style"]["true_scores"].append(y_true)
            results["whoop_style"]["calib_preds"].append(whoop_score / 100)
            results["whoop_style"]["calib_outs"].append(1 if y_true >= 70 else 0)

            # 在线更新
            observed = estimate_observed_recovery(
                f["hr"], f["rhr"], f["srpe"] > 0,
                self_reported_feeling=int(y_true / 10))
            model.update(f["intensity"], f["sleep_hours"],
                         f["hr"], f["rhr"], f["steps"], f["streak"],
                         observed)

    # ── 聚合 ──
    summary = {}
    method_labels = {
        "bayesian_online": "Bayesian (Ours)",
        "fixed_weights": "Fixed Weights",
        "whoop_style": "Whoop-Style",
    }
    for method, data in results.items():
        n = len(data["rmse"])
        if n == 0:
            continue
        rmse = math.sqrt(sum(data["rmse"]) / n)
        mae = sum(data["mae"]) / n
        calib = evaluate_calibration(data["calib_preds"], data["calib_outs"])

        # 皮尔逊相关系数：预测分数 vs 真实恢复分数
        corr = _pearson(data["pred_scores"], data["true_scores"])

        summary[method] = {
            "rmse": round(rmse, 2),
            "mae": round(mae, 2),
            "correlation": round(corr, 3),
            "ece": calib.get("ece", 0),
            "n_predictions": n,
            "method": method_labels[method],
        }

    # 计算贝叶斯 vs 固定的改善百分比
    if "bayesian_online" in summary and "fixed_weights" in summary:
        base_rmse = summary["fixed_weights"]["rmse"]
        bayes_rmse = summary["bayesian_online"]["rmse"]
        improvement = (base_rmse - bayes_rmse) / base_rmse * 100 if base_rmse > 0 else 0
        summary["improvement_pct"] = round(improvement, 1)

    return {
        "summary": summary,
        "dataset": "PMData",
        "citation": "Thambawita et al., MMSys 2020",
        "ground_truth": "Wellness Readiness (1-10)",
    }


def _pearson(x: list, y: list) -> float:
    n = len(x)
    if n < 3:
        return 0
    mx = sum(x) / n
    my = sum(y) / n
    sx = math.sqrt(sum((v - mx) ** 2 for v in x) / n)
    sy = math.sqrt(sum((v - my) ** 2 for v in y) / n)
    if sx == 0 or sy == 0:
        return 0
    return sum((x[i] - mx) * (y[i] - my) for i in range(n)) / (n * sx * sy)


def generate_recovery_latex_table(results: dict) -> str:
    """生成恢复评分对比的 LaTeX 表格。"""
    summary = results.get("summary", {})
    if not summary:
        return "% No results"

    lines = [
        r"\begin{table}[t]",
        r"\caption{Recovery Score Prediction Performance on PMData}",
        r"\label{tab:recovery}",
        r"\begin{tabular}{lcccc}",
        r"\toprule",
        r"Method & RMSE & MAE & Corr. & ECE \\",
        r"\midrule",
    ]
    for method in ["bayesian_online", "fixed_weights", "whoop_style"]:
        m = summary.get(method, {})
        if not m:
            continue
        lines.append(
            f"{m['method']} & {m['rmse']} & {m['mae']} & {m['correlation']:.3f} & {m['ece']:.3f} \\\\"
        )
    improv = summary.get("improvement_pct", 0)
    lines.append(r"\midrule")
    lines.append(f"Bayesian improvement over fixed weights & \\multicolumn{{4}}{{c}}{{{improv:.1f}\\%}} \\\\")
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "data/pmdata"
    print(f"Running recovery benchmark on {data_dir}...")
    t0 = time.perf_counter()
    r = run_recovery_benchmark(data_dir)
    elapsed = time.perf_counter() - t0
    print(f"Completed in {elapsed:.1f}s\n")

    for method, m in r["summary"].items():
        if not isinstance(m, dict):
            continue
        print(f"{m['method']}: RMSE={m['rmse']:.2f} MAE={m['mae']:.2f} "
              f"Corr={m['correlation']:.3f} ECE={m['ece']:.3f} n={m['n_predictions']}")

    if "improvement_pct" in r:
        print(f"\nBayesian improvement over fixed weights: {r['improvement_pct']:.1f}%")

    print()
    print(generate_recovery_latex_table(r))
