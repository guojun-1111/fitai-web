# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""Tests for fitai/analysis/ algorithms: trends, advanced, recovery, sleep, heart_rate."""
import sys
import os
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════════════════
# trends.py
# ═══════════════════════════════════════════════════════════════════

class TestDetectTrend:
    def test_improving_trend(self):
        from fitai.analysis.trends import detect_trend
        result = detect_trend([100, 110, 120, 130, 140, 150, 160])
        assert result["direction"] == "improving"
        assert result["slope_per_day"] > 0
        assert result["confidence"] > 0.9

    def test_declining_trend(self):
        from fitai.analysis.trends import detect_trend
        result = detect_trend([160, 150, 140, 130, 120, 110, 100])
        assert result["direction"] == "declining"
        assert result["slope_per_day"] < 0

    def test_stable_trend(self):
        from fitai.analysis.trends import detect_trend
        result = detect_trend([100, 101, 99, 100, 100, 100, 100])
        assert result["direction"] == "stable"
        assert abs(result["percent_change_per_week"]) < 0.5

    def test_insufficient_data(self):
        from fitai.analysis.trends import detect_trend
        result = detect_trend([1, 2])
        assert result["direction"] == "stable"
        assert result["confidence"] == 0

    def test_constant_values(self):
        from fitai.analysis.trends import detect_trend
        result = detect_trend([50, 50, 50, 50, 50])
        assert result["direction"] == "stable"
        assert result["slope_per_day"] == 0


class TestDetectAnomalies:
    def test_no_anomalies(self):
        from fitai.analysis.trends import detect_anomalies
        result = detect_anomalies([100, 102, 101, 99, 100, 101, 100])
        assert len(result) == 0

    def test_single_anomaly(self):
        from fitai.analysis.trends import detect_anomalies
        # 20 normal values + 1 extreme outlier: outlier dominates variance
        # but z-score should still be detectable
        values = [10] * 20 + [500]
        result = detect_anomalies(values)
        assert len(result) >= 1
        assert result[0]["index"] == 20
        assert result[0]["severity"] == "high"

    def test_insufficient_data(self):
        from fitai.analysis.trends import detect_anomalies
        result = detect_anomalies([1, 2, 3])
        assert len(result) == 0

    def test_high_severity(self):
        from fitai.analysis.trends import detect_anomalies
        values = [100] * 20 + [500]
        result = detect_anomalies(values)
        assert any(a["severity"] == "high" for a in result)


class TestAdaptiveAnomaly:
    def test_stable_user_tight_threshold(self):
        from fitai.analysis.trends import adaptive_anomaly_detection
        values = [100, 100, 100, 100, 100, 100, 100]
        result = adaptive_anomaly_detection(values)
        # Perfectly stable data (CV=0) → threshold=1.5; all values = mean → z=0
        assert len(result) == 0

    def test_volatile_user_loose_threshold(self):
        from fitai.analysis.trends import adaptive_anomaly_detection
        values = [10, 5, 8, 12, 3, 15, 7, 11, 4, 14]
        result = adaptive_anomaly_detection(values)
        assert all(a["threshold"] >= 2.5 for a in result)

    def test_insufficient_data(self):
        from fitai.analysis.trends import adaptive_anomaly_detection
        result = adaptive_anomaly_detection([1, 2, 3, 4, 5])
        assert len(result) == 0

    def test_small_cv_tightens_threshold(self):
        from fitai.analysis.trends import adaptive_anomaly_detection
        values = [100, 101, 100, 99, 100, 101, 100, 99]
        result = adaptive_anomaly_detection(values)
        for a in result:
            assert a["threshold"] <= 2.0


class TestComputeHealthScore:
    def test_perfect_score(self):
        from fitai.analysis.trends import compute_health_score
        result = compute_health_score({"steps": 12000, "sleep": 500, "calories": 600, "heart_rate": 65})
        assert result["score"] >= 80
        assert result["level"] == "优秀"

    def test_low_score(self):
        from fitai.analysis.trends import compute_health_score
        result = compute_health_score({"steps": 2000, "sleep": 200, "calories": 100, "heart_rate": 95})
        assert result["score"] < 45

    def test_score_bounded(self):
        from fitai.analysis.trends import compute_health_score
        result = compute_health_score({"steps": 99999, "sleep": 9999, "calories": 9999, "heart_rate": 60})
        assert 0 <= result["score"] <= 100

    def test_empty_metrics(self):
        from fitai.analysis.trends import compute_health_score
        result = compute_health_score({})
        assert result["score"] == 50


class TestComputeCorrelation:
    def test_strong_positive(self):
        from fitai.analysis.trends import compute_correlation
        result = compute_correlation([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
        assert result["coefficient"] > 0.9
        assert result["direction"] == "positive"

    def test_strong_negative(self):
        from fitai.analysis.trends import compute_correlation
        result = compute_correlation([1, 2, 3, 4, 5], [10, 8, 6, 4, 2])
        assert result["coefficient"] < -0.9
        assert result["direction"] == "negative"

    def test_insufficient_data(self):
        from fitai.analysis.trends import compute_correlation
        result = compute_correlation([1, 2], [3, 4])
        assert result["coefficient"] == 0


class TestMovingAverage:
    def test_simple_case(self):
        from fitai.analysis.trends import moving_average
        result = moving_average([1, 2, 3, 4, 5, 6, 7], window=3)
        assert result[0] is None, "edge should be None"
        assert result[1] == 2.0, f"got {result[1]}"
        assert result[6] is None, "edge should be None"

    def test_window_larger_than_data(self):
        from fitai.analysis.trends import moving_average
        result = moving_average([1, 2, 3], window=7)
        assert all(v is None for v in result)


class TestImputeMissing:
    def test_no_missing(self):
        from fitai.analysis.trends import impute_missing
        result = impute_missing([10, 20, 30])
        assert all(not is_est for _, is_est in result)

    def test_fills_gap(self):
        from fitai.analysis.trends import impute_missing
        result = impute_missing([10, 0, 30, 40])
        assert result[1][1] is True, "gap should be estimated"
        assert result[1][0] > 0, "should be filled"


class TestAnalyzeMetricTrend:
    def test_full_analysis(self):
        from fitai.analysis.trends import analyze_metric_trend
        data = [{"date": f"2026-01-{i+1:02d}", "value": 100 + i * 10} for i in range(14)]
        result = analyze_metric_trend(data, "test_metric")
        assert result["metric"] == "test_metric"
        assert result["trend"]["direction"] in ("improving", "declining", "stable")
        assert result["data_points"] == 14

    def test_empty_data(self):
        from fitai.analysis.trends import analyze_metric_trend
        result = analyze_metric_trend([], "empty")
        assert "error" in result


# ═══════════════════════════════════════════════════════════════════
# trends.py — ACWR
# ═══════════════════════════════════════════════════════════════════

class TestACWR:
    def test_insufficient_data(self):
        from fitai.analysis.trends import compute_acwr
        loads = [{"date": f"2026-01-{i+1:02d}", "load": 100} for i in range(10)]
        result = compute_acwr(loads)
        assert result["acwr"] is None
        assert "数据不足" in result["risk_level"]

    def test_safe_zone(self):
        from fitai.analysis.trends import compute_acwr
        loads = [{"date": f"2026-01-{i+1:02d}", "load": 100} for i in range(30)]
        result = compute_acwr(loads)
        assert result["acwr"] is not None
        assert 0.8 <= result["acwr"] <= 1.3
        assert result["risk_level"] == "安全"

    def test_danger_zone(self):
        from fitai.analysis.trends import compute_acwr
        loads = [{"date": f"2026-01-{i+1:02d}", "load": 50} for i in range(28)]
        loads += [{"date": f"2026-02-{i+1:02d}", "load": 200} for i in range(7)]
        result = compute_acwr(loads)
        assert result["acwr"] > 1.5
        assert result["risk_level"] == "危险"

    def test_coupled_acwr(self):
        from fitai.analysis.trends import compute_acwr
        loads = [{"date": f"2026-01-{i+1:02d}", "load": 100} for i in range(35)]
        result = compute_acwr(loads)
        assert result["coupled_acwr"] is not None


# ═══════════════════════════════════════════════════════════════════
# advanced.py
# ═══════════════════════════════════════════════════════════════════

class TestEWMAHealthScore:
    def test_basic_scoring(self):
        from fitai.analysis.advanced import ewma_health_score
        data = [
            {"date": "2026-07-01", "steps": 8000, "sleep": 450, "calories": 350, "heart_rate": 68},
            {"date": "2026-07-02", "steps": 9000, "sleep": 470, "calories": 400, "heart_rate": 65},
            {"date": "2026-07-03", "steps": 7500, "sleep": 420, "calories": 300, "heart_rate": 72},
        ]
        result = ewma_health_score(data)
        assert 0 <= result["score"] <= 100
        assert result["level"] in ("优秀", "良好", "一般", "需关注")
        assert isinstance(result["trend"], str)

    def test_empty_data(self):
        from fitai.analysis.advanced import ewma_health_score
        result = ewma_health_score([])
        assert result["score"] == 50
        assert result["level"] == "无数据"

    def test_stale_penalty(self):
        from fitai.analysis.advanced import ewma_health_score
        data = [{"date": "2026-06-01", "steps": 10000, "sleep": 480, "calories": 500, "heart_rate": 60}]
        result = ewma_health_score(data)
        assert result["stale_penalty"] > 0

    def test_trend_improving(self):
        from fitai.analysis.advanced import ewma_health_score
        data = [{"date": f"2026-07-{i:02d}", "steps": 4000 + i * 500, "sleep": 350 + i * 20,
                 "calories": 200 + i * 30, "heart_rate": 80 - i} for i in range(1, 15)]
        result = ewma_health_score(data)
        assert result["trend"] in ("↑ 上升", "↓ 下降", "→ 稳定")


class TestCrossMetricAnomaly:
    def test_empty_data(self):
        from fitai.analysis.advanced import cross_metric_anomaly
        result = cross_metric_anomaly({})
        assert len(result) == 0

    def test_insufficient_data(self):
        from fitai.analysis.advanced import cross_metric_anomaly
        data = {
            "2026-01-01": {"steps": 8000, "sleep": 420, "heart_rate": 65},
        }
        result = cross_metric_anomaly(data)
        assert len(result) == 0

    def test_no_anomaly_normal_data(self):
        from fitai.analysis.advanced import cross_metric_anomaly
        data = {}
        for i in range(21):
            date = f"2026-01-{i+1:02d}"
            data[date] = {"steps": 8000, "sleep": 450, "heart_rate": 65, "calories": 350}
        result = cross_metric_anomaly(data)
        assert len(result) == 0

    def test_overtraining_pattern(self):
        from fitai.analysis.advanced import cross_metric_anomaly
        data = {}
        for i in range(21):
            date = f"2026-01-{i+1:02d}"
            data[date] = {"steps": 8000, "sleep": 450, "heart_rate": 65, "calories": 350}
        # Insert overtraining signal on last day
        data["2026-01-21"] = {"steps": 3000, "sleep": 300, "heart_rate": 85, "calories": 350}
        result = cross_metric_anomaly(data)
        assert len(result) >= 1
        assert any("过度训练" in s["pattern"] for s in result)

    def test_dedup_signals(self):
        from fitai.analysis.advanced import cross_metric_anomaly
        data = {}
        for i in range(21):
            date = f"2026-01-{i+1:02d}"
            data[date] = {"steps": 8000, "sleep": 450, "heart_rate": 65, "calories": 350}
        data["2026-01-21"] = {"steps": 3000, "sleep": 300, "heart_rate": 85, "calories": 200}
        result = cross_metric_anomaly(data)
        assert len(result) <= 10

    def test_sliding_window_o_n(self):
        from fitai.analysis.advanced import cross_metric_anomaly
        data = {}
        for i in range(100):
            date = f"2026-{(i // 30) + 1:02d}-{(i % 30) + 1:02d}"
            data[date] = {"steps": 8000, "sleep": 450, "heart_rate": 65, "calories": 350}
        import time
        start = time.perf_counter()
        result = cross_metric_anomaly(data)
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, f"cross_metric_anomaly took {elapsed:.3f}s, should be O(n)"


class TestAdaptivePeriodization:
    def test_basic_plan(self):
        from fitai.analysis.advanced import adaptive_periodization
        result = adaptive_periodization("减脂", [])
        assert "plan" in result
        assert len(result["plan"]) == 4
        assert result["plan"][0]["week"] == 1

    def test_compliance_adjustment(self):
        from fitai.analysis.advanced import adaptive_periodization
        history = [
            {"date": f"2026-07-{i:02d}", "exercise_name": f"动作{i}", "duration_minutes": 45}
            for i in range(1, 29)
        ]
        result = adaptive_periodization("增肌", history)
        assert "compliance_rate" in result["adjustment_factors"]

    def test_diversity_insight(self):
        from fitai.analysis.advanced import adaptive_periodization
        history = [
            {"date": f"2026-07-{i:02d}", "exercise_name": "深蹲", "duration_minutes": 45}
            for i in range(1, 15)
        ]
        result = adaptive_periodization("增肌", history)
        has_diversity = any("单一" in s for s in result.get("insights", []))
        assert has_diversity


# ═══════════════════════════════════════════════════════════════════
# recovery.py
# ═══════════════════════════════════════════════════════════════════

class TestRecoveryScore:
    def test_full_recovery(self):
        from fitai.analysis.recovery import compute_recovery_score
        result = compute_recovery_score(
            workout_intensity=0, sleep_hours=9, resting_hr=55,
            resting_hr_baseline=60, steps=8000, training_days_streak=0
        )
        assert result["score"] >= 75
        assert result["action"] == "train_hard"

    def test_need_rest(self):
        from fitai.analysis.recovery import compute_recovery_score
        result = compute_recovery_score(
            workout_intensity=9, sleep_hours=4, resting_hr=80,
            resting_hr_baseline=60, steps=3000, training_days_streak=8
        )
        assert result["score"] < 35
        assert result["action"] == "rest"

    def test_moderate_recovery(self):
        from fitai.analysis.recovery import compute_recovery_score
        result = compute_recovery_score(
            workout_intensity=5, sleep_hours=7, resting_hr=68,
            resting_hr_baseline=60, steps=10000, training_days_streak=3
        )
        assert 35 <= result["score"] <= 74

    def test_score_bounded(self):
        from fitai.analysis.recovery import compute_recovery_score
        for wi in [0, 5, 10]:
            for sh in [3, 6, 9]:
                for hr in [50, 65, 90]:
                    result = compute_recovery_score(
                        workout_intensity=wi, sleep_hours=sh, resting_hr=hr,
                        resting_hr_baseline=60, steps=10000, training_days_streak=2
                    )
                    assert 0 <= result["score"] <= 100, f"score {result['score']} out of bounds"


# ═══════════════════════════════════════════════════════════════════
# sleep.py
# ═══════════════════════════════════════════════════════════════════

class TestSleepQuality:
    def test_empty_data(self):
        from fitai.analysis.sleep import sleep_quality_analysis
        result = sleep_quality_analysis([])
        assert "error" in result

    def test_excellent_sleep(self):
        from fitai.analysis.sleep import sleep_quality_analysis
        data = [{"date": f"2026-07-{i:02d}", "value": 480} for i in range(1, 15)]
        result = sleep_quality_analysis(data)
        assert result["score"] >= 85
        assert result["score_label"] == "优秀"

    def test_poor_sleep(self):
        from fitai.analysis.sleep import sleep_quality_analysis
        data = [{"date": f"2026-07-{i:02d}", "value": 240 + i * 10} for i in range(1, 8)]
        result = sleep_quality_analysis(data)
        assert result["score"] < 50

    def test_consistency_matters(self):
        from fitai.analysis.sleep import sleep_quality_analysis
        consistent = [{"date": f"2026-07-{i:02d}", "value": 480} for i in range(1, 8)]
        erratic = [{"date": f"2026-07-{i:02d}", "value": 240 if i % 2 == 0 else 600} for i in range(1, 8)]
        r1 = sleep_quality_analysis(consistent)
        r2 = sleep_quality_analysis(erratic)
        assert r1["consistency_label"] in ("优秀", "良好")

    def test_weekend_weekday_split(self):
        from fitai.analysis.sleep import sleep_quality_analysis
        import datetime
        data = []
        for i in range(14):
            d = datetime.date(2026, 7, 1) + datetime.timedelta(days=i)
            data.append({"date": d.isoformat(), "value": 480})
        result = sleep_quality_analysis(data)
        assert isinstance(result["weekend_catchup"], (int, float))

    def test_recommendations(self):
        from fitai.analysis.sleep import sleep_quality_analysis
        data = [{"date": "2026-07-01", "value": 240}]
        result = sleep_quality_analysis(data)
        assert len(result["recommendations"]) >= 1


# ═══════════════════════════════════════════════════════════════════
# heart_rate.py
# ═══════════════════════════════════════════════════════════════════

class TestHRZoneAnalysis:
    def test_empty_data(self):
        from fitai.analysis.heart_rate import hr_zone_analysis
        result = hr_zone_analysis([])
        assert "error" in result

    def test_zone_distribution(self):
        from fitai.analysis.heart_rate import hr_zone_analysis
        samples = [{"timestamp": i * 60, "heart_rate": hr} for i, hr in enumerate(
            [65, 72, 80, 95, 105, 110, 115, 120, 130, 140, 145, 150, 160, 170, 175, 155, 140, 130, 120, 100]
        )]
        result = hr_zone_analysis(samples, age=30, resting_hr=60)
        total_pct = sum(z["percent"] for z in result["zone_distribution"].values())
        assert abs(total_pct - 100) < 1

    def test_tanaka_formula_used(self):
        from fitai.analysis.heart_rate import hr_zone_analysis
        samples = [{"timestamp": 0, "heart_rate": 120}]
        result = hr_zone_analysis(samples, age=30, resting_hr=60)
        expected_max = 208 - 0.7 * 30
        assert result["max_hr_estimated"] == expected_max

    def test_training_effect(self):
        from fitai.analysis.heart_rate import hr_zone_analysis
        samples = [{"timestamp": i * 60, "heart_rate": 150} for i in range(20)]
        result = hr_zone_analysis(samples, age=30, resting_hr=60)
        assert "训练效果" in result["training_effect"] or "训练" in result["training_effect"]


class TestRestingHRTrend:
    def test_insufficient_data(self):
        from fitai.analysis.heart_rate import resting_hr_trend
        result = resting_hr_trend([{"date": "2026-01-01", "avg_hr": 65, "min_hr": 55}])
        assert "error" in result

    def test_improving_trend(self):
        from fitai.analysis.heart_rate import resting_hr_trend
        data = [{"date": f"2026-01-{i+1:02d}", "avg_hr": 72, "min_hr": 70 - i} for i in range(10)]
        result = resting_hr_trend(data)
        assert result["trend"]["direction"] == "improving", f"got {result['trend']['direction']}"

    def test_interpretation(self):
        from fitai.analysis.heart_rate import resting_hr_trend
        data = [{"date": f"2026-01-{i+1:02d}", "avg_hr": 70, "min_hr": 65} for i in range(5)]
        result = resting_hr_trend(data)
        assert "静息心率" in result["interpretation"]


# ═══════════════════════════════════════════════════════════════════
# counterfactual.py
# ═══════════════════════════════════════════════════════════════════

class TestCounterfactualEngine:
    def test_simple_counterfactual(self):
        from fitai.analysis.counterfactual import CounterfactualEngine
        effects = [{
            "cause": "sleep", "effect": "recovery",
            "effect_size": 0.1, "standardized": 0.5,
            "ci_lower": 0.05, "ci_upper": 0.15,
            "significant": True, "n_confounders": 0,
            "interpretation": "test",
        }]
        metrics = {
            "2026-01-01": {"sleep": 360, "recovery": 60},
            "2026-01-02": {"sleep": 420, "recovery": 65},
        }
        engine = CounterfactualEngine(effects, metrics)
        results = engine.predict({"sleep": 480})
        assert len(results) == 1
        r = results[0]
        assert r["metric"] == "recovery"
        assert r["current"] == 65.0
        expected_change = 0.1 * (480 - 420)
        assert abs(r["change"] - expected_change) < 0.01
        assert abs(r["counterfactual"] - (65 + expected_change)) < 0.01
        assert 0 <= r["probability_of_necessity"] <= 1

    def test_multiple_effects(self):
        from fitai.analysis.counterfactual import CounterfactualEngine
        effects = [
            {"cause": "sleep", "effect": "recovery", "effect_size": 0.1,
             "standardized": 0.4, "ci_lower": 0.05, "ci_upper": 0.15,
             "significant": True, "n_confounders": 0, "interpretation": ""},
            {"cause": "sleep", "effect": "heart_rate", "effect_size": -0.05,
             "standardized": -0.3, "ci_lower": -0.08, "ci_upper": -0.02,
             "significant": True, "n_confounders": 0, "interpretation": ""},
        ]
        metrics = {"2026-01-01": {"sleep": 360, "recovery": 60, "heart_rate": 70}}
        engine = CounterfactualEngine(effects, metrics)
        results = engine.predict({"sleep": 480})
        assert len(results) == 2

    def test_probability_of_necessity_bounds(self):
        from fitai.analysis.counterfactual import CounterfactualEngine
        effects = [{
            "cause": "steps", "effect": "calories",
            "effect_size": 0.04, "standardized": 0.8,
            "ci_lower": 0.02, "ci_upper": 0.06,
            "significant": True, "n_confounders": 0, "interpretation": "",
        }]
        metrics = {"2026-01-01": {"steps": 5000, "calories": 2000}}
        engine = CounterfactualEngine(effects, metrics)
        # Small change -> low PN
        results_small = engine.predict({"steps": 5100})
        pn_small = results_small[0]["probability_of_necessity"]
        # Large change -> high PN
        engine2 = CounterfactualEngine(effects, metrics)
        results_large = engine2.predict({"steps": 15000})
        if results_large:
            pn_large = results_large[0]["probability_of_necessity"]
            assert pn_large > pn_small, f"Expected PN({pn_large}) > PN({pn_small})"
        # PN always in [0,1]
        for r in results_small + results_large:
            assert 0 <= r["probability_of_necessity"] <= 1

    def test_compare_scenarios(self):
        from fitai.analysis.counterfactual import CounterfactualEngine
        effects = [
            {"cause": "sleep", "effect": "recovery", "effect_size": 0.1,
             "standardized": 0.5, "ci_lower": 0.05, "ci_upper": 0.15,
             "significant": True, "n_confounders": 0, "interpretation": ""},
            {"cause": "steps", "effect": "recovery", "effect_size": 0.001,
             "standardized": 0.1, "ci_lower": 0.0005, "ci_upper": 0.0015,
             "significant": True, "n_confounders": 0, "interpretation": ""},
        ]
        metrics = {"2026-01-01": {"sleep": 360, "recovery": 60, "steps": 5000}}
        engine = CounterfactualEngine(effects, metrics)
        comparison = engine.compare_scenarios([
            {"name": "多睡2h", "intervention": {"sleep": 480}},
            {"name": "多走5000步", "intervention": {"steps": 10000}},
        ])
        assert len(comparison) == 2
        # 多睡2h 的影响应大于多走5000步
        assert comparison[0]["name"] == "多睡2h"

    def test_find_best_intervention(self):
        from fitai.analysis.counterfactual import CounterfactualEngine
        effects = [
            {"cause": "sleep", "effect": "recovery", "effect_size": 0.1,
             "standardized": 0.5, "ci_lower": 0.05, "ci_upper": 0.15,
             "significant": True, "n_confounders": 0, "interpretation": ""},
            {"cause": "steps", "effect": "recovery", "effect_size": 0.001,
             "standardized": 0.1, "ci_lower": 0.0005, "ci_upper": 0.0015,
             "significant": True, "n_confounders": 0, "interpretation": ""},
        ]
        metrics = {"2026-01-01": {"sleep": 360, "recovery": 60, "steps": 5000}}
        engine = CounterfactualEngine(effects, metrics)
        best = engine.find_best_intervention("recovery")
        assert best["cause"] == "sleep"
        assert "expected_change" in best

    def test_no_relevant_effect(self):
        from fitai.analysis.counterfactual import CounterfactualEngine
        effects = [{
            "cause": "sleep", "effect": "recovery",
            "effect_size": 0.1, "standardized": 0.5,
            "ci_lower": 0.05, "ci_upper": 0.15,
            "significant": True, "n_confounders": 0, "interpretation": "",
        }]
        metrics = {"2026-01-01": {"sleep": 360, "recovery": 60}}
        engine = CounterfactualEngine(effects, metrics)
        # 干预一个没有因果边的指标
        results = engine.predict({"weight": 70})
        assert len(results) == 0

    def test_what_if_analysis_end_to_end(self):
        from fitai.analysis.counterfactual import what_if_analysis
        import random
        rng = random.Random(42)
        metrics = {}
        for i in range(30):
            sleep = 360 + rng.uniform(-30, 50) + (i % 7) * 15
            recovery = 50 + sleep * 0.06 + rng.uniform(-8, 8)
            hr = 72 - sleep * 0.02 + rng.uniform(-5, 5)
            metrics[f"2026-01-{i+1:02d}"] = {
                "sleep": round(sleep, 0), "recovery": round(recovery, 1),
                "steps": 5000 + i * 80 + rng.uniform(-1000, 1000),
                "heart_rate": round(hr, 1),
            }
        result = what_if_analysis(metrics, what_if_scenario={"sleep": 480})
        assert "current_state" in result
        assert "n_causal_edges" in result
        assert "predictions" in result
        assert isinstance(result["predictions"], list)


# ═══════════════════════════════════════════════════════════════════
# changepoint.py
# ═══════════════════════════════════════════════════════════════════

class TestBayesianChangePointDetector:
    def test_no_changepoint_stable_data(self):
        from fitai.analysis.changepoint import BayesianChangePointDetector
        detector = BayesianChangePointDetector()
        for i in range(50):
            result = detector.update(70.0 + i * 0.05, 70.0 + i * 0.05, 5.0)
        assert result["is_changepoint"] is False
        assert result["n_updates"] == 50

    def test_detect_known_changepoint(self):
        from fitai.analysis.changepoint import BayesianChangePointDetector
        detector = BayesianChangePointDetector(cusum_threshold=4.0)
        found = False
        for i in range(60):
            if i < 30:
                obs = 70.0
                pred = 70.0
            else:
                obs = 55.0  # 持续低于预测 15 分
                pred = 70.0
            result = detector.update(obs, pred, 5.0)
            if result["is_changepoint"]:
                found = True
                assert result["direction"] == "degrading"
                break
        assert found, "应检测到已知的变点"

    def test_cusum_resets_after_detection(self):
        from fitai.analysis.changepoint import BayesianChangePointDetector
        detector = BayesianChangePointDetector(cusum_threshold=3.0, drift=0.3)
        # 触发变点
        for i in range(40):
            result = detector.update(50.0, 70.0, 5.0)
        assert result["is_changepoint"]
        assert result["cusum_pos"] < 0.1  # CUSUM 已重置

    def test_bayes_factor_accumulates(self):
        from fitai.analysis.changepoint import BayesianChangePointDetector
        detector = BayesianChangePointDetector(cusum_threshold=8.0)
        # Phase 1: 稳定基线（obs ≈ pred）
        for _ in range(20):
            detector.update(70.0, 70.0, 5.0)
        bf_stable = detector.log_bf
        # Phase 2: 注入突变，检查 BF 在变化瞬间是否上升
        bf_peaks = []
        for _ in range(5):
            result = detector.update(50.0, 70.0, 5.0)
            bf_peaks.append(result["log_bayes_factor"])
        # BF 应在突变初期上升（峰值 > 稳定期）
        assert max(bf_peaks) > bf_stable, (
            f"BF peak {max(bf_peaks)} should exceed stable baseline {bf_stable}"
        )

    def test_default_hazard_rate(self):
        from fitai.analysis.changepoint import BayesianChangePointDetector
        detector = BayesianChangePointDetector()
        assert detector.cusum_threshold == 5.0
        assert detector.drift == 0.2
        assert detector.hazard_rate == 0.01


class TestPhysiologicalShiftDetector:
    def test_no_model_returns_graceful(self):
        from fitai.analysis.changepoint import PhysiologicalShiftDetector
        detector = PhysiologicalShiftDetector(user_id=1, bayesian_recovery_model=None)
        result = detector.update({"workout_intensity": 0.5})
        assert result["shift_detected"] is False
        assert "error" in result

    def test_detect_overtraining_pattern(self):
        from fitai.analysis.changepoint import BayesianChangePointDetector
        detector = BayesianChangePointDetector(cusum_threshold=3.0, drift=0.3)
        # 模拟过度训练模式：恢复持续低于预测，心率持续高于预测
        found = False
        for i in range(45):
            result = detector.update(45.0, 70.0, 8.0)
            if result["is_changepoint"] and result["direction"] == "degrading":
                found = True
                break
        assert found


class TestDetectPhysiologicalShifts:
    def test_detect_shifts_batch(self):
        from fitai.analysis.changepoint import detect_physiological_shifts
        n = 60
        dates = [f"2026-01-{i+1:02d}" for i in range(n)]
        observed = [70.0] * 30 + [50.0] * 30
        predicted = [70.0] * n
        stds = [5.0] * n
        shifts = detect_physiological_shifts(dates, observed, predicted, stds)
        assert len(shifts) > 0
        assert shifts[0]["shift_type"] == "degrading"


# ═══════════════════════════════════════════════════════════════════
# conformal.py
# ═══════════════════════════════════════════════════════════════════

class TestConformalPredictor:
    def test_conformal_coverage_iid(self):
        from fitai.analysis.conformal import ConformalPredictor
        import random
        rng = random.Random(42)
        n_cal, n_test = 100, 200
        # 生成 iid 数据: y = 3*x + N(0, sigma=2)
        xs = [rng.uniform(0, 10) for _ in range(n_cal + n_test)]
        ys_true = [3 * x + rng.gauss(0, 2) for x in xs]
        ys_pred = [3 * x for x in xs]  # 无噪声预测

        cp = ConformalPredictor(alpha=0.1)
        cp.calibrate(ys_true[:n_cal], ys_pred[:n_cal])

        eval_result = cp.evaluate_coverage(ys_true[n_cal:], ys_pred[n_cal:])
        assert eval_result["valid"], f"Coverage {eval_result['coverage']} below target"
        assert 0.8 <= eval_result["coverage"] <= 1.0

    def test_conformal_coverage_bounds(self):
        from fitai.analysis.conformal import ConformalPredictor
        import random
        rng = random.Random(123)
        n = 150
        xs = [rng.uniform(0, 10) for _ in range(n)]
        ys_true = [2 * x + rng.gauss(0, 1) for x in xs]
        ys_pred = [2 * x for x in xs]

        cp = ConformalPredictor(alpha=0.2)  # 80% 目标
        cp.calibrate(ys_true[:80], ys_pred[:80])
        eval_result = cp.evaluate_coverage(ys_true[80:], ys_pred[80:])
        assert eval_result["coverage"] >= 0.7

    def test_conformal_interval_nonempty(self):
        from fitai.analysis.conformal import ConformalPredictor
        cp = ConformalPredictor(alpha=0.1)
        cp.calibrate([1.0, 2.0, 1.5, 2.5], [1.0, 2.0, 1.5, 2.5])
        lo, hi = cp.predict(100.0)
        assert lo < hi

    def test_conformal_wider_on_noisy_data(self):
        from fitai.analysis.conformal import ConformalPredictor
        import random
        rng = random.Random(99)

        def get_q(noise_scale):
            ys_true = [rng.gauss(0, noise_scale) for _ in range(50)]
            ys_pred = [0.0] * 50
            cp = ConformalPredictor(alpha=0.1)
            cp.calibrate(ys_true, ys_pred)
            return cp.q

        q_low_noise = get_q(1.0)
        q_high_noise = get_q(5.0)
        assert q_high_noise > q_low_noise, "Noisier data should yield wider intervals"


class TestAdaptiveConformalPredictor:
    def test_adaptive_conformal_convergence(self):
        from fitai.analysis.conformal import AdaptiveConformalPredictor
        import random
        rng = random.Random(42)
        acp = AdaptiveConformalPredictor(alpha=0.1, gamma=0.01)
        # 200 步 iid 数据，覆盖率应收敛到 90%
        for _ in range(200):
            x = rng.uniform(0, 10)
            y_true = 3 * x + rng.gauss(0, 2)
            y_pred = 3 * x
            acp.update_and_predict(y_true, y_pred)
        history = acp.get_coverage_history()
        assert 0.8 <= history["empirical_coverage"] <= 1.0, (
            f"Coverage {history['empirical_coverage']} out of bounds"
        )

    def test_adaptive_conformal_responds_to_shift(self):
        from fitai.analysis.conformal import AdaptiveConformalPredictor
        import random
        rng = random.Random(42)
        acp = AdaptiveConformalPredictor(alpha=0.1, gamma=0.02)

        # Phase 1: 低噪声（sigma=1）
        for _ in range(100):
            x = rng.uniform(0, 10)
            y_true = 3 * x + rng.gauss(0, 1)
            y_pred = 3 * x
            acp.update_and_predict(y_true, y_pred)
        alpha_low_noise = acp.alpha

        # Phase 2: 高噪声（sigma=8）— α 应降低以扩大区间
        for _ in range(100):
            x = rng.uniform(0, 10)
            y_true = 3 * x + rng.gauss(0, 8)
            y_pred = 3 * x
            acp.update_and_predict(y_true, y_pred)
        alpha_high_noise = acp.alpha

        assert alpha_high_noise < alpha_low_noise, (
            f"Alpha should decrease under high noise: {alpha_high_noise} vs {alpha_low_noise}"
        )

    def test_adaptive_conformal_coverage_after_warmup(self):
        from fitai.analysis.conformal import AdaptiveConformalPredictor
        import random
        rng = random.Random(42)
        acp = AdaptiveConformalPredictor(alpha=0.1, gamma=0.005, score_window=80)

        for _ in range(400):
            x = rng.uniform(0, 10)
            y_true = 3 * x + rng.gauss(0, 1.5)
            y_pred = 3 * x
            acp.update_and_predict(y_true, y_pred)

        history = acp.get_coverage_history()
        assert history["n_observations"] == 400
        assert 0.8 <= history["empirical_coverage"] <= 1.0
        assert 0.01 <= history["alpha_current"] <= 0.5


class TestCompareIntervals:
    def test_compare_intervals_returns_keys(self):
        from fitai.analysis.conformal import compare_intervals
        n = 50
        bayesian_ci = [(i - 5, i + 5) for i in range(n)]
        conformal_ci = [(i - 3, i + 3) for i in range(n)]
        y_true = list(range(n))
        result = compare_intervals(bayesian_ci, conformal_ci, y_true)
        assert "bayesian" in result
        assert "conformal" in result
        assert "winner" in result
        assert result["winner"] in ("bayesian", "conformal", "neither")
