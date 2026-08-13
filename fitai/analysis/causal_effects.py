# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""V8.0: 因果效应估计 — 从"相关"到"改变多少"。

当前 causal_discovery.py 回答"X 和 Y 是否有因果关系"。
本模块进一步回答最关键的问题：

    "如果我改变 X，Y 会改变多少？"

例如：
- "每天多睡 1 小时，静息心率会降低多少 bpm？"
- "把步数从 5000 提到 10000，卡路里消耗会增加多少？"
- "减少训练强度 20%，恢复分数会提高多少？"

方法：基于学习到的因果图，用后门调整公式估计因果效应。
E[Y | do(X=x+δ)] - E[Y | do(X=x)]

参考：
- Pearl, J., 2009. "Causality" (2nd ed.), Ch.3 — 后门调整
- Maathuis et al., 2009. "Estimating high-dimensional intervention effects"
  (Annals of Statistics) — IDA 方法
"""
import math
from collections import defaultdict


def estimate_causal_effects(daily_metrics: dict, causal_graph: dict,
                             alpha: float = 0.05) -> list:
    """从观测数据和因果图中估计因果效应。

    使用后门调整公式：
    E[Y | do(X=x+δ)] = Σ_z E[Y | X=x+δ, Z=z] · P(Z=z)

    Z 是满足后门准则的变量集（X 的所有因果父节点）。

    Args:
        daily_metrics: {date: {metric: value, ...}, ...}
        causal_graph: {metric: [parent_metrics]} — 从 pc_stable() 返回
        alpha: 置信区间水平

    Returns:
        list of {"cause": X, "effect": Y, "effect_size": β, "ci": [lo, hi],
                 "interpretation": str}
    """
    sorted_dates = sorted(daily_metrics.keys())
    n = len(sorted_dates)
    if n < 14:
        return []

    # 提取所有数值指标
    metrics = set()
    for d in sorted_dates:
        for k, v in daily_metrics[d].items():
            if isinstance(v, (int, float)) and v > 0:
                metrics.add(k)
    metrics = sorted(metrics)

    # 按日期建立数据矩阵
    data = {m: [] for m in metrics}
    for d in sorted_dates:
        for m in metrics:
            val = daily_metrics[d].get(m, None)
            data[m].append(float(val) if val and val > 0 else None)

    # 填充缺失值
    for m in metrics:
        _fill_forward(data[m])

    # 估计每条有向边的因果效应
    effects = []
    for cause, targets in causal_graph.items():
        if cause not in data:
            continue
        for effect in targets:
            if effect not in data or effect == cause:
                continue

            # 找后门调整集：cause 的父节点（去掉 effect 以防循环）
            parents = [p for p in causal_graph.get(cause, [])
                       if p in data and p != effect]
            parents = list(set(parents))[:3]  # 最多 3 个父节点

            if not parents:
                # 无混杂 → 直接回归
                beta, ci = _simple_regression(data[cause], data[effect])
            else:
                # 有混杂 → 多元回归（后门调整）
                X = [[data[p][t] for p in parents] + [data[cause][t]]
                     for t in range(n) if all(data[m][t] is not None for m in [cause, effect] + parents)]
                Y = [data[effect][t] for t in range(n)
                     if all(data[m][t] is not None for m in [cause, effect] + parents)]
                if len(X) < 5:
                    continue
                # 取最后一个系数（cause 的系数）
                beta, ci = _multiple_regression(X, Y, len(parents))

            if abs(beta) < 1e-6:
                continue

            # 计算标准化效应量（Cohen's f²）
            mean_x = sum(v for v in data[cause] if v is not None) / max(
                sum(1 for v in data[cause] if v is not None), 1)
            mean_y = sum(v for v in data[effect] if v is not None) / max(
                sum(1 for v in data[effect] if v is not None), 1)
            standardized = beta * mean_x / mean_y if mean_y > 0 else beta

            # 生成可读解释
            interpretation = _interpret_effect(cause, effect, beta, standardized)

            effects.append({
                "cause": cause,
                "effect": effect,
                "effect_size": round(beta, 4),
                "standardized": round(standardized, 3),
                "ci_lower": round(ci[0], 4),
                "ci_upper": round(ci[1], 4),
                "significant": ci[0] * ci[1] > 0,  # CI 不跨零
                "n_confounders": len(parents),
                "interpretation": interpretation,
            })

    # 按标准化效应量降序
    effects.sort(key=lambda e: abs(e["standardized"]), reverse=True)
    return effects


def _fill_forward(series: list):
    """前向 + 后向填充缺失值。"""
    n = len(series)
    last = None
    for i in range(n):
        if series[i] is not None:
            last = series[i]
        elif last is not None:
            series[i] = last
    for i in range(n - 1, -1, -1):
        if series[i] is None:
            series[i] = last if last is not None else 0.0
        else:
            last = series[i]


def _simple_regression(x: list, y: list) -> tuple:
    """单变量线性回归（无混杂）。"""
    n = len(x)
    valid = [(xv, yv) for xv, yv in zip(x, y) if xv is not None and yv is not None]
    if len(valid) < 5:
        return 0.0, (0, 0)
    xv = [p[0] for p in valid]
    yv = [p[1] for p in valid]
    nv = len(xv)
    mx = sum(xv) / nv
    my = sum(yv) / nv
    num = sum((xv[i] - mx) * (yv[i] - my) for i in range(nv))
    den = sum((xv[i] - mx) ** 2 for i in range(nv))
    if abs(den) < 1e-10:
        return 0.0, (0, 0)
    beta = num / den
    residuals = [(yv[i] - my - beta * (xv[i] - mx)) ** 2 for i in range(nv)]
    se = math.sqrt(sum(residuals) / (nv - 2) / max(den, 1e-10))
    ci = (beta - 1.96 * se, beta + 1.96 * se)
    return beta, ci


def _multiple_regression(X: list, Y: list, cause_idx: int) -> tuple:
    """多元回归，返回 cause_idx 对应的系数。"""
    n = len(X)
    p = len(X[0])
    if n < p + 1:
        return 0.0, (0, 0)

    # 构造 (X^T X)^{-1} X^T Y
    XtX = [[0.0] * p for _ in range(p)]
    XtY = [0.0] * p
    for i in range(n):
        for j in range(p):
            XtY[j] += X[i][j] * Y[i]
            for k in range(p):
                XtX[j][k] += X[i][j] * X[i][k]

    # 求逆 (p ≤ 4, 小矩阵)
    XtX_inv = _invert_2d(XtX)
    if XtX_inv is None:
        return 0.0, (0, 0)

    # β = (X^T X)^{-1} X^T Y
    beta = [sum(XtX_inv[j][k] * XtY[k] for k in range(p)) for j in range(p)]

    # 标准误
    y_pred = [sum(beta[j] * X[i][j] for j in range(p)) for i in range(n)]
    rss = sum((Y[i] - y_pred[i]) ** 2 for i in range(n))
    sigma2 = rss / max(n - p, 1)
    se = math.sqrt(sigma2 * XtX_inv[cause_idx][cause_idx]) if cause_idx < p else 1.0

    beta_i = beta[cause_idx] if cause_idx < p else 0.0
    ci = (beta_i - 1.96 * se, beta_i + 1.96 * se)
    return beta_i, ci


def _invert_2d(A: list) -> list:
    """2D 矩阵求逆（高斯消元，p ≤ 4）。"""
    n = len(A)
    I = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    M = [[A[i][j] for j in range(n)] + I[i] for i in range(n)]

    for col in range(n):
        # 找主元
        pivot = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[pivot][col]) < 1e-12:
            return None
        M[col], M[pivot] = M[pivot], M[col]
        pivot_val = M[col][col]
        for j in range(2 * n):
            M[col][j] /= pivot_val
        for row in range(n):
            if row == col:
                continue
            factor = M[row][col]
            for j in range(2 * n):
                M[row][j] -= factor * M[col][j]

    return [[M[i][n + j] for j in range(n)] for i in range(n)]


def _interpret_effect(cause: str, effect: str, beta: float, std: float) -> str:
    """生成可读的因果效应解释。"""
    labels = {
        "steps": ("步数", "步", 1000),
        "sleep": ("睡眠", "分钟", 60),
        "heart_rate": ("心率", "bpm", 1),
        "resting_heart_rate": ("静息心率", "bpm", 1),
        "calories": ("卡路里消耗", "千卡", 100),
        "weight": ("体重", "kg", 1),
        "srpe": ("训练负荷", "sRPE单位", 50),
        "wellness_readiness": ("恢复准备度", "分", 1),
    }
    cause_label, cause_unit, cause_scale = labels.get(cause, (cause, "", 1))
    effect_label, effect_unit, _ = labels.get(effect, (effect, "", 1))

    change = beta * cause_scale
    direction = "增加" if change > 0 else "降低"

    if cause_unit:
        return (f"每{cause_unit}{cause_label}{direction} {abs(change):.1f}"
                f"{effect_unit}{effect_label}（标准化效应 {std:.2f}）")
    return f"{cause_label} → {effect_label}: β={beta:.4f}"


def generate_actionable_recommendations(effects: list) -> list:
    """从因果效应生成可操作的建议。"""
    recommendations = []
    for e in effects:
        if not e["significant"]:
            continue
        if e["cause"] == "sleep" and e["effect"] == "heart_rate":
            recommendations.append(
                f"多睡 1 小时 → 心率降低 {abs(e['effect_size']*60):.1f} bpm。"
                "提前 30 分钟上床是最有效的恢复策略。"
            )
        elif e["cause"] == "steps" and e["effect"] == "calories":
            recommendations.append(
                f"每多走 1000 步 → 多消耗 {e['effect_size']*1000:.0f} 千卡。"
                "午休散步 15 分钟可额外消耗 50-80 千卡。"
            )
        elif e["cause"] == "srpe" and e["effect"] == "wellness_readiness":
            if e["effect_size"] < 0:
                recommendations.append(
                    f"训练负荷每增加 {abs(e['effect_size']*50):.1f} 单位 → "
                    f"恢复准备度下降。高强度训练后建议安排 48h 恢复。"
                )
        elif e["cause"] == "sleep" and e["effect"] == "wellness_readiness":
            recommendations.append(
                f"睡眠每增加 1 小时 → 恢复准备度提高 {e['effect_size']*60:.1f} 分。"
                "睡眠是最被低估的恢复工具。"
            )

    return recommendations[:5]
