# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""V7.0 奇异谱分析（SSA）趋势分解与预测。

纯 Python 实现，零外部依赖。对个人健康数据的短时间序列（30-90 天）
进行趋势-周期-噪声分解，并给出带置信区间的预测。

计算量：60 天序列 × 30 天嵌入窗口，SVD of 31×30 矩阵 ≈ O(10^4) 运算，
在 1 核 CPU 上 < 10ms。

参考：
- Golyandina, N., Korobeynikov, A., Zhigljavsky, A., 2018.
  "Singular Spectrum Analysis for Time Series." Springer.
- Rodrigues et al., 2025, "SSA for Wearable Health Forecasting"
"""
import math


def ssa_decompose(values: list, window_len: int = None, n_components: int = 5) -> dict:
    """SSA 分解：将时间序列分解为趋势 + 周期 + 噪声分量。

    Args:
        values: 时间序列值（等间距）
        window_len: 嵌入窗口长度，默认 min(len(values)//2, 30)
        n_components: 保留的奇异值分量数

    Returns:
        dict with trend, periodic_components, noise, reconstructed, variance_explained
    """
    n = len(values)
    if n < 6:
        return {"error": "序列太短，至少需要 6 个数据点", "data_points": n}

    if window_len is None:
        window_len = min(n // 2, 30)
    window_len = max(3, min(window_len, n - 1))

    # ── 步骤1: 构建轨迹矩阵（Hankel）──
    K = n - window_len + 1  # 列数
    X = [[values[i + j] for j in range(K)] for i in range(window_len)]
    # X: window_len × K 矩阵

    # ── 步骤2: SVD（幂迭代取前 n_components 个分量）──
    svd_result = _svd_power_iteration(X, n_components)
    U = svd_result["U"]  # window_len × r
    S = svd_result["S"]  # r singular values
    V = svd_result["V"]  # K × r

    # 计算每个分量解释的方差比例
    total_variance = sum(s * s for s in S)
    variance_explained = [round(s * s / total_variance * 100, 1) if total_variance > 0 else 0
                          for s in S]

    # ── 步骤3: 分量分类（趋势 vs 周期 vs 噪声）──
    components = []
    for k in range(len(S)):
        comp = _reconstruct_component(U, V, S, k, window_len, K, n)
        components.append(comp)

    classified = _classify_components(components, S, variance_explained)

    # ── 步骤4: 重构各分量 ──
    trend_raw = [0.0] * n
    periodics = []
    noise = [0.0] * n

    for k, comp in enumerate(components):
        if k in classified["trend_indices"]:
            for i in range(n):
                trend_raw[i] += comp[i]
        elif k in classified["periodic_indices"]:
            periodics.append({
                "component_index": k,
                "values": [round(v, 3) for v in comp],
                "variance_pct": variance_explained[k],
                "dominant_freq": _estimate_frequency(comp),
            })
        else:
            for i in range(n):
                noise[i] += comp[i]

    # 平滑趋势（简单移动平均去锯齿）
    trend = _smooth_trend(trend_raw, window=3)

    # 重构序列
    reconstructed = [round(trend[i] + sum(p["values"][i] for p in periodics), 3)
                     for i in range(n)]

    return {
        "trend": [round(v, 3) for v in trend],
        "periodic_components": periodics,
        "noise": [round(v, 3) for v in noise],
        "reconstructed": reconstructed,
        "variance_explained": variance_explained,
        "component_count": len(S),
        "window_len": window_len,
        "data_points": n,
    }


def ssa_forecast(values: list, steps: int = 7, window_len: int = None) -> dict:
    """SSA 预测：基于分解后的趋势和周期分量进行前向预测。

    使用循环预测（recurrent forecasting）：利用趋势分量在边界处的值
    作为初始条件，递推预测未来值。

    Args:
        values: 历史时间序列
        steps: 预测步数（默认 7 天）
        window_len: 嵌入窗口长度

    Returns:
        dict with forecast, confidence_interval, trend_direction, trend_strength
    """
    decomp = ssa_decompose(values, window_len)
    if "error" in decomp:
        return {"error": decomp["error"]}

    n = len(values)
    trend = decomp["trend"]

    # ── 趋势外推 ──
    # 取趋势最后 window_len 个值，拟合局部线性趋势
    trend_tail = trend[-max(3, len(trend) // 3):]
    if len(trend_tail) >= 3:
        # 简单线性外推
        t_vals = list(range(len(trend_tail)))
        mean_t = sum(t_vals) / len(t_vals)
        mean_v = sum(trend_tail) / len(trend_tail)
        slope_num = sum((t_vals[i] - mean_t) * (trend_tail[i] - mean_v) for i in range(len(t_vals)))
        slope_den = sum((t_vals[i] - mean_t) ** 2 for i in range(len(t_vals)))
        slope = slope_num / slope_den if slope_den > 0 else 0
    else:
        slope = 0

    # 预测值
    last_trend = trend[-1]
    forecast = []
    for i in range(1, steps + 1):
        forecast.append(round(last_trend + slope * i, 2))

    # ── 置信区间（基于噪声标准差）──
    noise = decomp["noise"]
    noise_var = sum(v * v for v in noise) / max(len(noise), 1)
    noise_std = math.sqrt(noise_var) if noise_var > 0 else 0

    ci_lower = [round(f - 1.96 * noise_std * math.sqrt(i), 2) for i, f in enumerate(forecast, 1)]
    ci_upper = [round(f + 1.96 * noise_std * math.sqrt(i), 2) for i, f in enumerate(forecast, 1)]

    # ── 趋势方向与强度 ──
    if slope > 0.5:
        direction = "上升"
    elif slope < -0.5:
        direction = "下降"
    else:
        direction = "稳定"

    mean_val = sum(values) / len(values) if values else 1
    strength = abs(slope / mean_val * 100) if mean_val > 0 else 0
    if strength < 0.3:
        trend_strength = "微弱"
    elif strength < 1.0:
        trend_strength = "中等"
    else:
        trend_strength = "显著"

    # ── 周期性预测叠加 ──
    if decomp["periodic_components"]:
        main_periodic = max(decomp["periodic_components"], key=lambda p: p["variance_pct"])
        period_len = max(1, main_periodic.get("dominant_freq", 7))
        periodic = main_periodic["values"]
        for i in range(steps):
            forecast[i] += periodic[-(period_len - i % period_len) % period_len - 1]

    return {
        "forecast": forecast,
        "confidence_interval": {
            "lower": ci_lower,
            "upper": ci_upper,
            "std_error": round(noise_std, 2),
        },
        "trend_direction": direction,
        "trend_strength": trend_strength,
        "slope_per_step": round(slope, 3),
        "data_points": n,
        "forecast_steps": steps,
    }


# ═══════════════════════════════════════════════════════════════════
# 内部实现
# ═══════════════════════════════════════════════════════════════════

def _svd_power_iteration(X: list, k: int) -> dict:
    """幂迭代 SVD：取前 k 个奇异值和奇异向量。

    对矩阵 X (m×n)，使用子空间迭代（block power iteration）计算
    最大的 k 个奇异值及对应的左右奇异向量。适用于小矩阵。
    """
    m = len(X)
    n = len(X[0])
    k = min(k, min(m, n))

    if k == 0:
        return {"U": [[0]], "S": [0], "V": [[0]]}

    # 初始随机向量（确保数值稳定性）
    Q = [[_rand_normal() for _ in range(n)] for __ in range(k)]
    Q = _qr_orthonormalize(Q)

    # 幂迭代（通常 5-10 轮就收敛）
    for _ in range(10):
        # 乘 X^T
        Z = [[0.0] * n for _ in range(k)]
        for r in range(k):
            for j in range(n):
                s = 0.0
                for i in range(m):
                    s += Q[r][i] * X[i][j]
                Z[r][j] = s

        # 乘 X
        Y = [[0.0] * m for _ in range(k)]
        for r in range(k):
            for i in range(m):
                s = 0.0
                for j in range(n):
                    s += Z[r][j] * X[i][j]
                Y[r][i] = s

        Q = _qr_orthonormalize(Y)

    # 计算奇异值和奇异向量
    # 右奇异向量 V = X^T Q（n×k 的转置，即 k×n）
    Vt = [[0.0] * n for _ in range(k)]
    for r in range(k):
        for j in range(n):
            s = 0.0
            for i in range(m):
                s += Q[r][i] * X[i][j]
            Vt[r][j] = s

    # 归一化右奇异向量，奇异值 = 范数
    S = [0.0] * k
    for r in range(k):
        norm = math.sqrt(sum(Vt[r][j] ** 2 for j in range(n)))
        S[r] = norm
        if norm > 1e-12:
            for j in range(n):
                Vt[r][j] /= norm

    # 对应重排左奇异向量（如果符号翻转的话）
    U_cols = []
    for r in range(k):
        Ui = [Q[r][i] for i in range(m)]
        U_cols.append(Ui)

    return {
        "U": [[U_cols[r][i] for r in range(k)] for i in range(m)],  # m × k
        "S": S,  # k
        "V": [[Vt[r][j] for r in range(k)] for j in range(n)],  # n × k
    }


def _reconstruct_component(U: list, V: list, S: list, k: int,
                           window_len: int, K: int, n: int) -> list:
    """从第 k 个 SVD 分量重构时间序列（对角平均/hankelization）。"""
    # 重构矩阵 X_k = s_k * u_k * v_k^T
    sk = S[k]
    Xk = [[0.0] * K for _ in range(window_len)]
    for i in range(window_len):
        u_ik = U[i][k] if k < len(U[i]) else 0
        for j in range(K):
            v_jk = V[j][k] if k < len(V[j]) else 0
            Xk[i][j] = sk * u_ik * v_jk

    # 对角平均
    result = [0.0] * n
    counts = [0] * n

    for i in range(window_len):
        for j in range(K):
            idx = i + j
            if idx < n:
                result[idx] += Xk[i][j]
                counts[idx] += 1

    for i in range(n):
        if counts[i] > 0:
            result[i] /= counts[i]

    return result


def _classify_components(components: list, S: list, variance_pct: list) -> dict:
    """将 SSA 分量分类为趋势、周期和噪声。

    分类规则：
    - 趋势分量：变化缓慢（相邻值相关性高），且方差占比大
    - 周期分量：有明确的零交叉模式
    - 噪声分量：其余
    """
    n = len(components[0]) if components else 0
    trend_indices = []
    periodic_indices = []
    noise_indices = []

    for k in range(len(S)):
        comp = components[k]
        if variance_pct[k] < 3.0:
            noise_indices.append(k)
            continue

        # 趋势检测：相邻值相关性
        if n >= 5:
            mean_c = sum(comp) / n
            cov = sum((comp[i] - mean_c) * (comp[i + 1] - mean_c) for i in range(n - 1)) / (n - 1)
            var_c = sum((comp[i] - mean_c) ** 2 for i in range(n)) / n
            autocorr = cov / var_c if var_c > 1e-12 else 0

            # 计数零穿越次数
            zero_crossings = sum(1 for i in range(n - 1)
                                 if (comp[i] >= 0) != (comp[i + 1] >= 0))

            if autocorr > 0.7 and zero_crossings <= 2:
                trend_indices.append(k)
            elif zero_crossings >= 3:
                periodic_indices.append(k)
            else:
                noise_indices.append(k)
        else:
            noise_indices.append(k)

    return {
        "trend_indices": trend_indices,
        "periodic_indices": periodic_indices,
        "noise_indices": noise_indices,
    }


def _estimate_frequency(component: list) -> int:
    """估算周期分量的主导周期长度（天数）。"""
    n = len(component)
    if n < 4:
        return 7

    # 零穿越法：平均周期 = 2 * n / (零穿越次数)
    zero_crossings = sum(1 for i in range(n - 1)
                         if (component[i] >= 0) != (component[i + 1] >= 0))
    if zero_crossings >= 1:
        period = max(1, int(2 * n / zero_crossings))
    else:
        period = 7

    return min(period, 30)


def _smooth_trend(trend: list, window: int = 3) -> list:
    """简单移动平均平滑趋势线。"""
    n = len(trend)
    if n < window:
        return [round(v, 3) for v in trend]

    result = []
    half = window // 2
    for i in range(n):
        start = max(0, i - half)
        end = min(n, i + half + 1)
        result.append(round(sum(trend[start:end]) / (end - start), 3))
    return result


def _qr_orthonormalize(vectors: list) -> list:
    """修正 Gram-Schmidt 正交归一化。"""
    k = len(vectors)
    if k == 0:
        return vectors
    m = len(vectors[0]) if vectors else 0
    if m == 0:
        return vectors

    Q = [[v for v in row] for row in vectors]
    for i in range(k):
        # 减去投影
        for j in range(i):
            dot = sum(Q[i][t] * Q[j][t] for t in range(m))
            for t in range(m):
                Q[i][t] -= dot * Q[j][t]
        # 归一化
        norm = math.sqrt(sum(Q[i][t] ** 2 for t in range(m)))
        if norm > 1e-14:
            for t in range(m):
                Q[i][t] /= norm
        else:
            # 退化：用随机向量重新初始化
            for t in range(m):
                Q[i][t] = _rand_normal()

    return Q


def _rand_normal() -> float:
    """Box-Muller 变换生成标准正态随机数。"""
    import random
    u1 = max(random.random(), 1e-10)
    u2 = random.random()
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
