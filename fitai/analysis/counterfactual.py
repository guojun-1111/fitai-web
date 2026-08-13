# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""V9.0: 反事实预测引擎 — Pearl 因果层级 Level 3。

当前 causal_effects.py 回答 Level 2 问题："睡眠对心率的影响有多大？"
本模块回答 Level 3 问题："如果我昨晚多睡 2 小时，今天的心率会是多少？"

Level 2 = E[Y | do(X=x')]           — 平均干预效应
Level 3 = E[Y_{x'} | X=x, Y=y]     — 个体反事实（给定我已知道实际值）

对于线性高斯 SCM，反事实有闭式解：
  Y = α_y + β·X + γ·Z + U_y
  → U_y = y - α_y - β·x - γ·Z      (Abduction)
  → Y_{x'} = α_y + β·x' + γ·Z + U_y  (Prediction under do(X=x'))
  → Y_{x'} = y + β·(x' - x)         (Z 和 α_y 消掉了！)

关键洞察：反事实预测不需要知道混杂因子 Z 或截距 α_y。
只需当前观测值 y、因果效应 β、干预差值 (x' - x)。

参考：
- Pearl, J., 2009. "Causality" (2nd ed.), Ch.7 — 反事实
- Pearl, G., & Mackenzie, D., 2018. "The Book of Why", Ch.8
- Balke, A., & Pearl, J., 1994. "Counterfactual Probabilities"
"""
import math


class CounterfactualEngine:
    """反事实推理引擎。

    给定因果效应估计和观测数据，预测"如果X不同，Y会是多少"。

    用法:
        effects = estimate_causal_effects(metrics, graph)
        engine = CounterfactualEngine(effects, metrics)
        results = engine.predict({"sleep": 480})  # 如果睡 8 小时
    """

    def __init__(self, causal_effects: list, daily_metrics: dict):
        """初始化引擎。

        Args:
            causal_effects: estimate_causal_effects() 的返回值
            daily_metrics: {date: {metric: value}}，用于提取当前状态
        """
        self._effects = causal_effects
        self._current = self._extract_current_state(daily_metrics)
        self._effect_lookup = self._build_lookup(causal_effects)

    def _extract_current_state(self, daily_metrics: dict) -> dict:
        """从 daily_metrics 提取最新一天的各指标值。"""
        if not daily_metrics:
            return {}
        sorted_dates = sorted(daily_metrics.keys())
        latest = daily_metrics[sorted_dates[-1]]
        state = {}
        for k, v in latest.items():
            if isinstance(v, (int, float)) and v > 0:
                state[k] = float(v)
        return state

    def _build_lookup(self, effects: list) -> dict:
        """构建 {cause: {effect: entry}} 查找表。"""
        lookup = {}
        for e in effects:
            cause = e["cause"]
            effect = e["effect"]
            if cause not in lookup:
                lookup[cause] = {}
            lookup[cause][effect] = e
        return lookup

    def predict(self, what_if: dict) -> list:
        """预测「如果改变 X，Y 会变成多少」。

        Args:
            what_if: {"sleep": 480, "steps": 12000} — 假设的干预值

        Returns:
            [{metric, current, counterfactual, change, ci_lower, ci_upper,
              probability_of_necessity, cause, interpretation}]
        """
        results = []
        seen_effects = {}  # effect -> best result (largest |change|)

        for cause, new_val in what_if.items():
            if cause not in self._current or cause not in self._effect_lookup:
                continue
            old_val = self._current[cause]
            delta_x = new_val - old_val
            if abs(delta_x) < 1e-6:
                continue

            for effect, entry in self._effect_lookup[cause].items():
                if effect not in self._current:
                    continue
                beta = entry["effect_size"]
                old_y = self._current[effect]
                change = beta * delta_x
                new_y = old_y + change

                se_beta = (entry["ci_upper"] - entry["ci_lower"]) / (2 * 1.96)
                se_change = abs(delta_x) * max(se_beta, 1e-10)
                ci_lo = change - 1.96 * se_change
                ci_hi = change + 1.96 * se_change

                mean_x = old_val if old_val > 0 else 1
                sigma_resid = abs(beta * mean_x / max(abs(entry["standardized"]), 0.001))
                sigma_resid = max(sigma_resid, se_change)
                pn = _normal_cdf(abs(change) / max(sigma_resid, 1e-10))

                key = effect
                if key not in seen_effects or abs(change) > abs(seen_effects[key]["change"]):
                    direction = "增加" if change > 0 else "降低"
                    seen_effects[key] = {
                        "metric": effect,
                        "current": round(old_y, 2),
                        "counterfactual": round(new_y, 2),
                        "change": round(change, 2),
                        "ci_lower": round(ci_lo, 2),
                        "ci_upper": round(ci_hi, 2),
                        "probability_of_necessity": round(pn, 3),
                        "significant": entry["significant"],
                        "cause": cause,
                        "interpretation": (
                            f"如果{cause}从{old_val:.0f}{direction}到{new_val:.0f}，"
                            f"{effect}预计从{old_y:.1f}变为{new_y:.1f}"
                            f"（变化{change:+.1f}，PN={pn:.0%}）"
                        ),
                    }

        return sorted(seen_effects.values(), key=lambda r: abs(r["change"]), reverse=True)

    def compare_scenarios(self, scenarios: list) -> list:
        """比较多个「如果」方案。

        Args:
            scenarios: [{"name": "早睡2h", "intervention": {"sleep": 480}}, ...]

        Returns:
            [{name, results: [...]}] 按总影响排序
        """
        comparisons = []
        for s in scenarios:
            results = self.predict(s["intervention"])
            total_impact = sum(abs(r["change"]) for r in results)
            comparisons.append({
                "name": s["name"],
                "intervention": s["intervention"],
                "results": results,
                "total_impact": round(total_impact, 2),
                "n_effects": len(results),
            })
        comparisons.sort(key=lambda c: c["total_impact"], reverse=True)
        return comparisons

    def find_best_intervention(self, target_metric: str,
                               max_changes: dict = None) -> dict:
        """找到对目标指标影响最大的干预。

        Args:
            target_metric: 想优化的指标（如 "recovery_score"）
            max_changes: 各指标的可行最大改变量 {"sleep": 120, "steps": 5000}

        Returns:
            {cause, current_value, recommended_value, expected_change, confidence}
        """
        best = None
        best_change = 0

        for cause, effects in self._effect_lookup.items():
            if target_metric not in effects:
                continue
            entry = effects[target_metric]
            if not entry["significant"]:
                continue
            if cause not in self._current:
                continue

            beta = entry["effect_size"]
            current_cause = self._current[cause]
            # 默认改变量：当前值的 20%，或 max_changes 中的指定值
            if max_changes and cause in max_changes:
                delta = max_changes[cause]
            else:
                delta = current_cause * (0.2 if beta > 0 else -0.2)
            if abs(delta) < 1e-6:
                continue

            change = beta * delta
            if abs(change) > abs(best_change):
                best_change = change
                best = {
                    "cause": cause,
                    "current_value": round(current_cause, 1),
                    "recommended_value": round(current_cause + delta, 1),
                    "expected_change": round(change, 2),
                    "effect_size": round(beta, 4),
                    "confidence": "高" if abs(entry["standardized"]) > 0.5 else "中",
                    "rationale": (
                        f"将{cause}从{current_cause:.0f}调整到{current_cause + delta:.0f}，"
                        f"预计{target_metric}变化{change:+.1f}"
                    ),
                }

        return best if best else {"error": "无有效干预方案", "target": target_metric}


def what_if_analysis(daily_metrics: dict, causal_graph: dict = None,
                     what_if_scenario: dict = None) -> dict:
    """一键反事实分析：PC-stable → 因果效应 → 反事实。

    Args:
        daily_metrics: {date: {metric: value}}
        causal_graph: pc_stable() 返回的 causal graph（可选，不传则自动计算）
        what_if_scenario: 干预场景 {"sleep": 480}

    Returns:
        {current_state, scenario, predictions, best_intervention}
    """
    if causal_graph is None:
        from fitai.analysis.causal_discovery import pc_stable
        discovery = pc_stable(daily_metrics)
        causal_graph = discovery.get("graph", {})

    from fitai.analysis.causal_effects import estimate_causal_effects
    effects = estimate_causal_effects(daily_metrics, causal_graph)

    engine = CounterfactualEngine(effects, daily_metrics)

    result = {
        "current_state": engine._current,
        "n_causal_edges": len(effects),
        "n_significant_edges": sum(1 for e in effects if e["significant"]),
    }

    if what_if_scenario:
        result["scenario"] = what_if_scenario
        result["predictions"] = engine.predict(what_if_scenario)
        if result["predictions"]:
            first_effect = result["predictions"][0]["metric"]
            result["best_intervention"] = engine.find_best_intervention(first_effect)
    else:
        result["message"] = "未指定干预场景，返回引擎实例以调用 .predict()"

    return result


def _normal_cdf(x: float) -> float:
    """标准正态 CDF（Abramowitz & Stegun 近似）。"""
    if x < -8:
        return 0.0
    if x > 8:
        return 1.0
    a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    p = 0.3275911
    sign = 1 if x >= 0 else -1
    x = abs(x)
    t = 1.0 / (1.0 + p * x)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x / 2.0)
    return 0.5 * (1.0 + sign * y)
