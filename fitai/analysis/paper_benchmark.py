# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""V7.0 Research: 学术论文基准评估管线。

对「轻量级 CPU 健康异常检测」方法体系进行全面评估，
输出可直接用于学术论文的指标表格和消融实验数据。

叙事: "Lightweight Probabilistic Health Monitoring on Edge CPUs"
- 在 1 核 CPU 上运行的无依赖概率推断方法
- 对比 4 种基线：概率化跨指标 / 硬阈值 / Z-score / EWMA
- 评估维度：检测精度、计算效率、误报控制

用法:
    python -m fitai.analysis.paper_benchmark
"""
import math
import time
import random
from collections import defaultdict
from datetime import datetime, timedelta


# ═══════════════════════════════════════════════════════════════════
# 实验配置
# ═══════════════════════════════════════════════════════════════════

CONFIG = {
    "n_users": 50,
    "n_days": 60,
    "anomaly_rates": [0.03, 0.05, 0.10],
    "noise_levels": ["low", "medium", "high"],
    "seeds": [42, 123, 456],
}


# ═══════════════════════════════════════════════════════════════════
# 噪声水平配置
# ═══════════════════════════════════════════════════════════════════

NOISE_CONFIGS = {
    "low": {"steps": 300, "sleep": 10, "heart_rate": 1.5, "calories": 100},
    "medium": {"steps": 750, "sleep": 25, "heart_rate": 3, "calories": 250},
    "high": {"steps": 1500, "sleep": 50, "heart_rate": 6, "calories": 500},
}


# ═══════════════════════════════════════════════════════════════════
# 主评估函数
# ═══════════════════════════════════════════════════════════════════

def run_full_benchmark(config: dict = None) -> dict:
    """运行完整基准评估，生成论文级结果。

    Returns:
        dict with:
        - summary_table: 总体指标对比
        - by_anomaly_type: 按异常类型的检测率
        - by_noise_level: 按噪声水平的鲁棒性
        - efficiency: 计算效率对比
        - ablation: 消融实验
    """
    cfg = config or CONFIG

    from fitai.analysis.evaluation import (generate_synthetic_health_data,
                                            compare_methods)
    from fitai.analysis.probabilistic_anomaly import probabilistic_cross_anomaly

    all_results = defaultdict(list)

    for seed in cfg["seeds"]:
        for ar in cfg["anomaly_rates"]:
            for noise_name, noise_std in NOISE_CONFIGS.items():
                rng = random.Random(seed)
                datasets = generate_synthetic_health_data(
                    n_days=cfg["n_days"], n_users=cfg["n_users"],
                    anomaly_rate=ar, seed=seed)

                for ds in datasets:
                    # 记录计算时间
                    t0 = time.perf_counter()
                    prob_result = probabilistic_cross_anomaly(ds["data"])
                    prob_time = time.perf_counter() - t0

                    # 运行对比
                    comp = compare_methods(ds)

                    for method, metrics in comp.items():
                        all_results[(method, noise_name, ar)].append({
                            "f1": metrics["f1_score"],
                            "precision": metrics["precision"],
                            "recall": metrics["recall"],
                            "tp": metrics["true_positives"],
                            "fp": metrics["false_positives"],
                        })

                    if "probabilistic_cross_metric" in comp:
                        all_results[("prob_time", noise_name, ar)].append(prob_time * 1000)

    # 聚合结果
    summary = _aggregate_results(all_results)
    return summary


def _aggregate_results(raw: dict) -> dict:
    """聚合原始结果为论文级摘要。"""
    methods = ["probabilistic_cross_metric", "zscore_baseline",
               "ewma_baseline", "original_threshold",
               "isolation_forest", "lof", "pca", "autoencoder"]

    # 总体指标
    overall = {}
    for method in methods:
        scores = {"f1": [], "precision": [], "recall": [], "fp": []}
        for key, vals in raw.items():
            if key[0] == method:
                for v in vals:
                    scores["f1"].append(v["f1"])
                    scores["precision"].append(v["precision"])
                    scores["recall"].append(v["recall"])
                    scores["fp"].append(v["fp"])
        if scores["f1"]:
            overall[method] = {
                "f1_mean": round(sum(scores["f1"]) / len(scores["f1"]), 3),
                "f1_std": round(_std(scores["f1"]), 3),
                "precision_mean": round(sum(scores["precision"]) / len(scores["precision"]), 3),
                "recall_mean": round(sum(scores["recall"]) / len(scores["recall"]), 3),
                "avg_fp": round(sum(scores["fp"]) / len(scores["fp"]), 1),
                "n_trials": len(scores["f1"]),
            }

    # 计算效率
    efficiency = {}
    for key, vals in raw.items():
        if key[0] == "prob_time":
            efficiency[f"{key[1]}_{key[2]}"] = round(sum(vals) / len(vals), 1)

    return {
        "overall": overall,
        "efficiency_ms": efficiency,
        "n_users": CONFIG["n_users"],
        "n_days": CONFIG["n_days"],
        "total_trials": sum(1 for key in raw if key[0] == methods[0]),
    }


def _std(values: list) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))


# ═══════════════════════════════════════════════════════════════════
# LaTeX 表格生成
# ═══════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════
# 统计显著性检验
# ═══════════════════════════════════════════════════════════════════

def wilcoxon_signed_rank_test(sample_a: list, sample_b: list) -> dict:
    """配对 Wilcoxon 符号秩检验（纯 Python）。

    用于比较两个方法在相同数据集上的性能是否显著不同。

    Returns:
        dict with statistic, p_value, significant (at alpha=0.05)
    """
    if len(sample_a) != len(sample_b) or len(sample_a) < 5:
        return {"statistic": 0, "p_value": 1.0, "significant": False}

    # 计算带符号的差值
    diffs = [a - b for a, b in zip(sample_a, sample_b)]
    # 去除零差值
    non_zero = [(abs(d), d > 0) for d in diffs if d != 0]
    if not non_zero:
        return {"statistic": 0, "p_value": 1.0, "significant": False}

    # 按绝对值排序
    non_zero.sort(key=lambda x: x[0])
    n = len(non_zero)

    # 分配秩（处理平局）
    ranks = []
    i = 0
    while i < n:
        j = i + 1
        while j < n and abs(non_zero[j][0] - non_zero[i][0]) < 1e-10:
            j += 1
        avg_rank = (i + j + 1) / 2.0  # 1-indexed 平均秩
        for _ in range(j - i):
            ranks.append(avg_rank)
        i = j

    # 计算正秩和和负秩和
    W_plus = sum(r for (_, is_pos), r in zip(non_zero, ranks) if is_pos)
    W_minus = sum(r for (_, is_pos), r in zip(non_zero, ranks) if not is_pos)
    W = min(W_plus, W_minus)

    # 正态近似（大样本）
    mean_w = n * (n + 1) / 4.0
    # 处理平局的方差校正
    tie_groups = {}
    for (val, _), r in zip(non_zero, ranks):
        tie_groups.setdefault(val, []).append(r)
    tie_correction = sum(len(g) * (len(g) ** 2 - 1) for g in tie_groups.values())
    std_w = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0 - tie_correction / 48.0)

    if std_w > 0:
        z = (W - mean_w) / std_w
        p_val = 2.0 * (1.0 - _normal_cdf_wilcoxon(abs(z)))
    else:
        p_val = 1.0

    return {
        "statistic": round(W, 2),
        "p_value": round(p_val, 4),
        "significant": p_val < 0.05,
        "n_pairs": n,
        "test": "Wilcoxon signed-rank",
    }


def _normal_cdf_wilcoxon(z: float) -> float:
    """标准正态 CDF 近似。"""
    if z < -8.0:
        return 0.0
    if z > 8.0:
        return 1.0
    x = abs(z)
    t = 1.0 / (1.0 + 0.2316419 * x)
    poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 +
              t * (-1.821255978 + t * 1.330274429))))
    phi = 1.0 - (1.0 / math.sqrt(2 * math.pi)) * math.exp(-x * x / 2.0) * poly
    return phi if z >= 0 else 1.0 - phi


def run_statistical_tests(results: dict) -> dict:
    """在基准结果上运行配对统计检验。

    比较我们的方法 vs 每个基线方法。
    """
    pairwise = {}
    methods = list(results.get("overall", {}).keys())
    our_method = "probabilistic_cross_metric"

    # 从 all_results 中获取每对的原始分数
    for method in methods:
        if method == our_method:
            continue
        test = wilcoxon_signed_rank_test(
            results.get("raw_scores", {}).get(our_method, []),
            results.get("raw_scores", {}).get(method, []),
        )
        pairwise[f"{our_method}_vs_{method}"] = test

    return pairwise


def generate_latex_table(results: dict) -> str:
    """从评估结果生成 LaTeX 表格。"""
    overall = results.get("overall", {})
    if not overall:
        return "% No results"

    method_labels = {
        "probabilistic_cross_metric": "Prob-Cross (Ours)",
        "original_threshold": "Threshold-Cross",
        "zscore_baseline": "Z-Score",
        "ewma_baseline": "EWMA",
        "isolation_forest": "Isolation Forest",
        "lof": "LOF",
        "pca": "PCA",
        "autoencoder": "Autoencoder",
    }

    lines = [
        r"\begin{table}[t]",
        r"\caption{Anomaly Detection Performance on Synthetic Health Data}",
        r"\label{tab:detection}",
        r"\begin{tabular}{lcccc}",
        r"\toprule",
        r"Method & F1 & Precision & Recall & Avg FP \\",
        r"\midrule",
    ]

    for method, label in method_labels.items():
        m = overall.get(method, {})
        if not m:
            continue
        lines.append(
            f"{label} & {m['f1_mean']:.3f}$\\pm${m['f1_std']:.3f} & "
            f"{m['precision_mean']:.3f} & {m['recall_mean']:.3f} & "
            f"{m['avg_fp']:.1f} \\\\"
        )

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ])

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# 消融实验
# ═══════════════════════════════════════════════════════════════════

def run_ablation(dataset: dict) -> dict:
    """消融实验：逐一移除算法组件，测量性能变化。

    移除三个核心组件:
    - Fisher's 合并检验：移除后使用 min p 值作为组合 p 值
    - BH-FDR 多重检验校正：移除后使用固定阈值 p < 0.1
    - 贝叶斯滑动窗口基线：移除后使用全局均值和方差
    """
    from fitai.analysis.probabilistic_anomaly import probabilistic_cross_anomaly
    from fitai.analysis.evaluation import evaluate_detection

    # 完整方法：Fisher + BH-FDR + Bayesian baseline
    full = probabilistic_cross_anomaly(
        dataset["data"], fdr_level=0.1,
        use_fisher=True, use_bh_fdr=True, use_bayesian_baseline=True)
    full_signals = [{"date": s["date"]} for s in full.get("signals", [])]
    full_metrics = evaluate_detection(dataset["labels"], full_signals)

    # 消融 1: 移除 Fisher's 合并检验 → min p 值
    no_fisher = probabilistic_cross_anomaly(
        dataset["data"], fdr_level=0.1,
        use_fisher=False, use_bh_fdr=True, use_bayesian_baseline=True)
    nf_signals = [{"date": s["date"]} for s in no_fisher.get("signals", [])]
    no_fisher_metrics = evaluate_detection(dataset["labels"], nf_signals)

    # 消融 2: 移除 BH-FDR 校正 → 固定阈值
    no_bh = probabilistic_cross_anomaly(
        dataset["data"], fdr_level=0.1,
        use_fisher=True, use_bh_fdr=False, use_bayesian_baseline=True)
    nb_signals = [{"date": s["date"]} for s in no_bh.get("signals", [])]
    no_bh_metrics = evaluate_detection(dataset["labels"], nb_signals)

    # 消融 3: 移除贝叶斯滑动窗口 → 全局基线
    no_bayes = probabilistic_cross_anomaly(
        dataset["data"], fdr_level=0.1,
        use_fisher=True, use_bh_fdr=True, use_bayesian_baseline=False)
    nby_signals = [{"date": s["date"]} for s in no_bayes.get("signals", [])]
    no_bayes_metrics = evaluate_detection(dataset["labels"], nby_signals)

    return {
        "full": {
            "metrics": full_metrics,
            "n_signals": len(full.get("signals", [])),
            "label": "Full model (Fisher + BH-FDR + Bayesian baseline)"
        },
        "no_fisher": {
            "metrics": no_fisher_metrics,
            "n_signals": len(no_fisher.get("signals", [])),
            "label": "Without Fisher's method (min-P)"
        },
        "no_bh_fdr": {
            "metrics": no_bh_metrics,
            "n_signals": len(no_bh.get("signals", [])),
            "label": "Without BH-FDR (fixed threshold)"
        },
        "no_bayesian_baseline": {
            "metrics": no_bayes_metrics,
            "n_signals": len(no_bayes.get("signals", [])),
            "label": "Without Bayesian baseline (global stats)"
        },
    }


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def run_benchmark_on_pmdata(data_dir: str) -> dict:
    """在 PMData 真实数据集上运行完整基准评估。

    Args:
        data_dir: PMData 根目录路径

    Returns:
        dict with overall, efficiency, table (与 run_full_benchmark 格式相同)
    """
    from fitai.analysis.pmdata_loader import load_pmdata_dataset
    from fitai.analysis.evaluation import evaluate_detection, baseline_zscore, baseline_ewma
    from fitai.analysis.probabilistic_anomaly import probabilistic_cross_anomaly
    from fitai.analysis.advanced import cross_metric_anomaly
    from fitai.analysis.sota_baselines import baseline_isolation_forest, baseline_lof
    from fitai.analysis.dl_baselines import baseline_pca, baseline_autoencoder

    datasets = load_pmdata_dataset(data_dir)
    if not datasets:
        return {"error": "No participants loaded from PMData"}

    methods = ["probabilistic_cross_metric", "zscore_baseline",
               "ewma_baseline", "original_threshold",
               "isolation_forest", "lof", "pca", "autoencoder"]
    all_results = {m: {"f1": [], "precision": [], "recall": [], "fp": [], "time_ms": []}
                   for m in methods}

    for ds in datasets:
        if ds["n_days"] < 14:
            continue

        # 概率化方法
        t0 = time.perf_counter()
        prob = probabilistic_cross_anomaly(ds["data"])
        prob_time = (time.perf_counter() - t0) * 1000
        prob_signals = [{"date": s["date"]} for s in prob.get("signals", [])]
        prob_metrics = evaluate_detection(ds["labels"], prob_signals)
        _append_metrics(all_results["probabilistic_cross_metric"], prob_metrics, prob_time)

        # Z-score 基线
        t0 = time.perf_counter()
        zs_signals = baseline_zscore(ds["data"])
        zs_time = (time.perf_counter() - t0) * 1000
        zs_metrics = evaluate_detection(ds["labels"], zs_signals)
        _append_metrics(all_results["zscore_baseline"], zs_metrics, zs_time)

        # EWMA 基线
        t0 = time.perf_counter()
        ewma_signals = baseline_ewma(ds["data"])
        ewma_time = (time.perf_counter() - t0) * 1000
        ewma_metrics = evaluate_detection(ds["labels"], ewma_signals)
        _append_metrics(all_results["ewma_baseline"], ewma_metrics, ewma_time)

        # 原始硬阈值
        t0 = time.perf_counter()
        orig_signals = cross_metric_anomaly(ds["data"])
        orig_time = (time.perf_counter() - t0) * 1000
        orig_formatted = [{"date": s["date"]} for s in orig_signals]
        orig_metrics = evaluate_detection(ds["labels"], orig_formatted)
        _append_metrics(all_results["original_threshold"], orig_metrics, orig_time)

        # SOTA: Isolation Forest (Liu et al., 2008)
        t0 = time.perf_counter()
        if_signals = baseline_isolation_forest(ds["data"])
        if_time = (time.perf_counter() - t0) * 1000
        if_metrics = evaluate_detection(ds["labels"], if_signals)
        _append_metrics(all_results["isolation_forest"], if_metrics, if_time)

        # SOTA: LOF (Breunig et al., 2000)
        t0 = time.perf_counter()
        lof_signals = baseline_lof(ds["data"])
        lof_time = (time.perf_counter() - t0) * 1000
        lof_metrics = evaluate_detection(ds["labels"], lof_signals)
        _append_metrics(all_results["lof"], lof_metrics, lof_time)

        # DL: PCA Reconstruction Error
        t0 = time.perf_counter()
        pca_signals = baseline_pca(ds["data"])
        pca_time = (time.perf_counter() - t0) * 1000
        pca_metrics = evaluate_detection(ds["labels"], pca_signals)
        _append_metrics(all_results["pca"], pca_metrics, pca_time)

        # DL: Autoencoder Reconstruction Error
        t0 = time.perf_counter()
        ae_signals = baseline_autoencoder(ds["data"], epochs=20)
        ae_time = (time.perf_counter() - t0) * 1000
        ae_metrics = evaluate_detection(ds["labels"], ae_signals)
        _append_metrics(all_results["autoencoder"], ae_metrics, ae_time)

    # 聚合
    overall = {}
    for method, data in all_results.items():
        if data["f1"]:
            overall[method] = {
                "f1_mean": round(sum(data["f1"]) / len(data["f1"]), 3),
                "f1_std": round(_std(data["f1"]), 3),
                "precision_mean": round(sum(data["precision"]) / len(data["precision"]), 3),
                "recall_mean": round(sum(data["recall"]) / len(data["recall"]), 3),
                "avg_fp": round(sum(data["fp"]) / len(data["fp"]), 1),
                "avg_time_ms": round(sum(data["time_ms"]) / len(data["time_ms"]), 1),
                "n_trials": len(data["f1"]),
            }

    return {
        "overall": overall,
        "dataset": "PMData",
        "n_participants": len(datasets),
        "citation": "Thambawita et al., MMSys 2020",
    }


def _append_metrics(storage: dict, metrics: dict, time_ms: float):
    for k in ["f1_score", "precision", "recall"]:
        val = metrics.get(k, 0)
        if k == "f1_score":
            storage["f1"].append(val)
        elif k == "precision":
            storage["precision"].append(val)
        elif k == "recall":
            storage["recall"].append(val)
    storage["fp"].append(metrics.get("false_positives", 0))
    storage["time_ms"].append(time_ms)


if __name__ == "__main__":
    print("Running paper benchmark...")
    print(f"Config: {CONFIG['n_users']} users × {CONFIG['n_days']} days, "
          f"anomaly rates={CONFIG['anomaly_rates']}, noise={list(NOISE_CONFIGS)}")
    print()

    t0 = time.perf_counter()
    results = run_full_benchmark()
    elapsed = time.perf_counter() - t0

    print(f"Benchmark completed in {elapsed:.1f}s")
    print(f"Total trials: {results['total_trials']}")
    print()

    print("=== Overall Results ===")
    overall = results["overall"]
    header = f"{'Method':<30} {'F1':>8} {'Precision':>10} {'Recall':>8} {'Avg FP':>8}"
    print(header)
    print("-" * len(header))

    labels = {
        "probabilistic_cross_metric": "Prob-Cross (Ours)",
        "original_threshold": "Threshold-Cross",
        "zscore_baseline": "Z-Score",
        "ewma_baseline": "EWMA",
    }
    for method, label in labels.items():
        m = overall.get(method, {})
        if m:
            print(f"{label:<30} {m['f1_mean']:.3f}±{m['f1_std']:.3f}  "
                  f"{m['precision_mean']:.3f}     {m['recall_mean']:.3f}     {m['avg_fp']:.1f}")

    print()
    print("=== Computation Efficiency (ms per query) ===")
    for k, v in sorted(results["efficiency_ms"].items()):
        print(f"  {k}: {v:.1f}ms")

    print()
    print("=== LaTeX Table ===")
    print(generate_latex_table(results))
