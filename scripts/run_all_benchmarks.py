# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""运行所有真实数据基准测试，输出 JSON 结果用于论文。

用法:
    python scripts/run_all_benchmarks.py
    python scripts/run_all_benchmarks.py --output ../benchmark_results/
"""
import json
import os
import sys
import time
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def run_anomaly_benchmark(datasets: list, dataset_name: str) -> dict:
    """在给定数据集上运行 8 方法异常检测对比。"""
    from fitai.analysis.probabilistic_anomaly import probabilistic_cross_anomaly
    from fitai.analysis.advanced import cross_metric_anomaly
    from fitai.analysis.evaluation import evaluate_detection, baseline_zscore, baseline_ewma
    from fitai.analysis.sota_baselines import baseline_isolation_forest, baseline_lof
    from fitai.analysis.dl_baselines import baseline_pca, baseline_autoencoder

    methods = ["probabilistic_cross_metric", "zscore_baseline", "ewma_baseline",
               "original_threshold", "isolation_forest", "lof", "pca", "autoencoder"]
    all_results = {m: {"f1": [], "precision": [], "recall": [], "fp": [], "time_ms": []}
                   for m in methods}

    per_user = []
    for ds in datasets:
        if ds["n_days"] < 14:
            continue

        user_result = {"user_id": ds["user_id"], "n_days": ds["n_days"]}

        # 1. 概率化跨指标（我们的方法）
        t0 = time.perf_counter()
        prob = probabilistic_cross_anomaly(ds["data"])
        prob_time = (time.perf_counter() - t0) * 1000
        prob_signals = [{"date": s["date"]} for s in prob.get("signals", [])]
        prob_metrics = evaluate_detection(ds["labels"], prob_signals)
        _append(all_results["probabilistic_cross_metric"], prob_metrics, prob_time)
        user_result["prob_cross"] = {"fp": prob_metrics["false_positives"], "time_ms": prob_time}

        # 2. Z-score
        t0 = time.perf_counter()
        zs_signals = baseline_zscore(ds["data"])
        zs_time = (time.perf_counter() - t0) * 1000
        zs_metrics = evaluate_detection(ds["labels"], zs_signals)
        _append(all_results["zscore_baseline"], zs_metrics, zs_time)

        # 3. EWMA
        t0 = time.perf_counter()
        ewma_signals = baseline_ewma(ds["data"])
        ewma_time = (time.perf_counter() - t0) * 1000
        ewma_metrics = evaluate_detection(ds["labels"], ewma_signals)
        _append(all_results["ewma_baseline"], ewma_metrics, ewma_time)

        # 4. 原始硬阈值
        t0 = time.perf_counter()
        orig_signals = cross_metric_anomaly(ds["data"])
        orig_time = (time.perf_counter() - t0) * 1000
        orig_formatted = [{"date": s["date"]} for s in orig_signals]
        orig_metrics = evaluate_detection(ds["labels"], orig_formatted)
        _append(all_results["original_threshold"], orig_metrics, orig_time)

        # 5. Isolation Forest
        t0 = time.perf_counter()
        if_signals = baseline_isolation_forest(ds["data"])
        if_time = (time.perf_counter() - t0) * 1000
        if_metrics = evaluate_detection(ds["labels"], if_signals)
        _append(all_results["isolation_forest"], if_metrics, if_time)

        # 6. LOF
        t0 = time.perf_counter()
        lof_signals = baseline_lof(ds["data"])
        lof_time = (time.perf_counter() - t0) * 1000
        lof_metrics = evaluate_detection(ds["labels"], lof_signals)
        _append(all_results["lof"], lof_metrics, lof_time)

        # 7. PCA
        t0 = time.perf_counter()
        pca_signals = baseline_pca(ds["data"])
        pca_time = (time.perf_counter() - t0) * 1000
        pca_metrics = evaluate_detection(ds["labels"], pca_signals)
        _append(all_results["pca"], pca_metrics, pca_time)

        # 8. Autoencoder
        t0 = time.perf_counter()
        ae_signals = baseline_autoencoder(ds["data"], epochs=20)
        ae_time = (time.perf_counter() - t0) * 1000
        ae_metrics = evaluate_detection(ds["labels"], ae_signals)
        _append(all_results["autoencoder"], ae_metrics, ae_time)

        per_user.append(user_result)

    # 聚合
    overall = {}
    for method, data in all_results.items():
        if data["f1"]:
            n = len(data["f1"])
            overall[method] = {
                "f1_mean": round(sum(data["f1"]) / n, 3),
                "f1_std": round(_std(data["f1"]), 3),
                "precision_mean": round(sum(data["precision"]) / n, 3),
                "recall_mean": round(sum(data["recall"]) / n, 3),
                "avg_fp": round(sum(data["fp"]) / n, 1),
                "avg_time_ms": round(sum(data["time_ms"]) / n, 1),
                "n_trials": n,
            }

    return {
        "overall": overall,
        "dataset": dataset_name,
        "n_participants": len(datasets),
        "n_evaluated": len(per_user),
        "per_user": per_user,
    }


def run_ablation_all(datasets: list) -> dict:
    """在所有参与者上运行消融实验。"""
    from fitai.analysis.probabilistic_anomaly import probabilistic_cross_anomaly
    from fitai.analysis.evaluation import evaluate_detection

    variants = {
        "full": {"use_fisher": True, "use_bh_fdr": True, "use_bayesian_baseline": True},
        "no_fisher": {"use_fisher": False, "use_bh_fdr": True, "use_bayesian_baseline": True},
        "no_bh_fdr": {"use_fisher": True, "use_bh_fdr": False, "use_bayesian_baseline": True},
        "no_bayesian": {"use_fisher": True, "use_bh_fdr": True, "use_bayesian_baseline": False},
    }

    agg = {k: {"fp": [], "n_signals": []} for k in variants}

    for ds in datasets:
        if ds["n_days"] < 14:
            continue
        for name, params in variants.items():
            result = probabilistic_cross_anomaly(ds["data"], fdr_level=0.1, **params)
            signals = [{"date": s["date"]} for s in result.get("signals", [])]
            metrics = evaluate_detection(ds["labels"], signals)
            agg[name]["fp"].append(metrics["false_positives"])
            agg[name]["n_signals"].append(len(result.get("signals", [])))

    summary = {}
    for name, data in agg.items():
        if data["fp"]:
            summary[name] = {
                "avg_fp": round(sum(data["fp"]) / len(data["fp"]), 1),
                "avg_n_signals": round(sum(data["n_signals"]) / len(data["n_signals"]), 1),
                "n_trials": len(data["fp"]),
                "label": list(variants[name].values()),
            }

    # 计算变化百分比（相对于 full model）
    if "full" in summary:
        full_fp = summary["full"]["avg_fp"]
        for name in summary:
            if name != "full" and full_fp > 0:
                pct = (summary[name]["avg_fp"] - full_fp) / full_fp * 100
                summary[name]["fp_change_pct"] = round(pct, 1)

    return summary


def _append(container: dict, metrics: dict, time_ms: float):
    container["f1"].append(metrics.get("f1_score", 0))
    container["precision"].append(metrics.get("precision", 0))
    container["recall"].append(metrics.get("recall", 0))
    container["fp"].append(metrics.get("false_positives", 0))
    container["time_ms"].append(time_ms)


def _std(values: list) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return (sum((v - mean) ** 2 for v in values) / (n - 1)) ** 0.5


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=None, help="Output directory for JSON results")
    args = parser.parse_args()

    if args.output:
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = Path(__file__).resolve().parent.parent / "data"

    results = {}

    # ── PMData ──
    print("=" * 60)
    print("Loading PMData...")
    from fitai.analysis.pmdata_loader import load_pmdata_dataset
    pmdata = load_pmdata_dataset("data/pmdata")
    print(f"  {len(pmdata)} participants loaded")

    print("Running anomaly benchmark on PMData...")
    t0 = time.perf_counter()
    results["pmdata_anomaly"] = run_anomaly_benchmark(pmdata, "PMData")
    print(f"  Done in {time.perf_counter() - t0:.1f}s")

    print("Running ablation on PMData...")
    t0 = time.perf_counter()
    results["pmdata_ablation"] = run_ablation_all(pmdata)
    print(f"  Done in {time.perf_counter() - t0:.1f}s")

    # ── Kaggle Fitbit ──
    print("=" * 60)
    print("Loading Kaggle Fitbit...")
    from fitai.analysis.kaggle_loader import load_kaggle_dataset
    kaggle = load_kaggle_dataset("data/fitbit")
    print(f"  {len(kaggle)} participants loaded")

    print("Running anomaly benchmark on Kaggle Fitbit...")
    t0 = time.perf_counter()
    results["kaggle_anomaly"] = run_anomaly_benchmark(kaggle, "Kaggle Fitbit")
    print(f"  Done in {time.perf_counter() - t0:.1f}s")

    print("Running ablation on Kaggle Fitbit...")
    t0 = time.perf_counter()
    results["kaggle_ablation"] = run_ablation_all(kaggle)
    print(f"  Done in {time.perf_counter() - t0:.1f}s")

    # ── Recovery Benchmark ──
    print("=" * 60)
    print("Running recovery benchmark on PMData...")
    from fitai.analysis.recovery_benchmark import run_recovery_benchmark
    t0 = time.perf_counter()
    results["pmdata_recovery"] = run_recovery_benchmark("data/pmdata")
    print(f"  Done in {time.perf_counter() - t0:.1f}s")

    # ── Save ──
    print("=" * 60)
    out_path = out_dir / "benchmark_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"Results saved to {out_path} ({out_path.stat().st_size} bytes)")

    # ── Print Summary ──
    print("\n" + "=" * 60)
    print("ANOMALY DETECTION — PMData")
    print("=" * 60)
    for method, m in results["pmdata_anomaly"]["overall"].items():
        print(f"  {method:30s}: F1={m['f1_mean']:.3f} P={m['precision_mean']:.3f} "
              f"R={m['recall_mean']:.3f} FP={m['avg_fp']:.1f}/user time={m['avg_time_ms']:.1f}ms")

    print("\nANOMALY DETECTION — Kaggle Fitbit")
    print("=" * 60)
    for method, m in results["kaggle_anomaly"]["overall"].items():
        print(f"  {method:30s}: F1={m['f1_mean']:.3f} P={m['precision_mean']:.3f} "
              f"R={m['recall_mean']:.3f} FP={m['avg_fp']:.1f}/user time={m['avg_time_ms']:.1f}ms")

    print("\nABLATION — PMData")
    print("=" * 60)
    for name, m in results["pmdata_ablation"].items():
        pct = m.get("fp_change_pct", "")
        print(f"  {name:25s}: FP={m['avg_fp']:.1f}/user signals={m['avg_n_signals']:.1f} "
              f"Δ={pct:+.1f}%" if pct != "" else f"  {name:25s}: FP={m['avg_fp']:.1f}/user signals={m['avg_n_signals']:.1f}")

    print("\nRECOVERY — PMData")
    print("=" * 60)
    for method, m in results["pmdata_recovery"].get("summary", {}).items():
        if isinstance(m, dict):
            print(f"  {m['method']:25s}: RMSE={m['rmse']:.2f} MAE={m['mae']:.2f} "
                  f"Corr={m['correlation']:.3f} ECE={m['ece']:.3f}")


if __name__ == "__main__":
    main()
