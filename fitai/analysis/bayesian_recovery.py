# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""V7.0 在线贝叶斯恢复模型。

用贝叶斯线性回归（Normal-Inverse-Gamma 共轭先验，闭合解，无需 MCMC）
替代 recovery.py 中的固定权重。每个用户的个性化恢复系数通过
每天的数据在线更新。

计算量：k=5 特征，每次更新 O(k²)=O(25)，在 1 核 CPU 上可忽略不计。

参考：
- Murphy, 2023, "Probabilistic Machine Learning: Advanced Topics", Ch. 2
- Nakamura et al., 2024, "Personalized Recovery Prediction Using Wearable Data"
"""
import math
from datetime import datetime, timedelta


# ═══════════════════════════════════════════════════════════════════
# 贝叶斯线性回归核心
# ═══════════════════════════════════════════════════════════════════

class BayesianRecoveryModel:
    """在线贝叶斯线性回归模型，用于个性化恢复评分。

    使用 Normal-Inverse-Gamma 共轭先验，每次新数据到达时
    通过闭合公式更新后验，无需 MCMC 采样。
    """

    def __init__(self, prior_weights: list = None):
        """初始化模型。

        Args:
            prior_weights: 先验权重 [w0, w1, ..., w5]，对应：
                [截距, 训练强度, 睡眠, 心率偏差, 步数, 连续训练天数]
                默认使用 recovery.py 的固定权重转换而来。
        """
        self.k = 6  # 特征数量（含截距）
        self.n = 0  # 已观测样本数

        # 先验超参数
        # β ~ N(μ₀, σ²Λ₀⁻¹)
        if prior_weights:
            self.mu = list(prior_weights)
        else:
            # 默认先验：基于 recovery.py 的规则权重
            self.mu = [60.0, -2.0, 1.5, -1.0, 0.0005, -1.5]
        # Λ₀ = λ * I（先验精度矩阵）
        self.prior_precision = 0.1  # λ：先验强度，小值 = 弱先验（让数据主导）
        self.Lambda = [[self.prior_precision if i == j else 0.0 for j in range(self.k)]
                       for i in range(self.k)]

        # σ² ~ IG(a₀, b₀)
        self.a0 = 3.0  # 形状参数
        self.b0 = 100.0  # 尺度参数（预期 σ² ≈ 100，即 std ≈ 10 分）

        # 后验参数（初始 = 先验）
        self.a_n = self.a0
        self.b_n = self.b0

        # 存储最近的特征和历史预测用于诊断
        self.recent_features = []
        self.recent_outcomes = []
        self.last_update = None

    def _extract_features(self, workout_intensity: float, sleep_hours: float,
                          hr_deviation: float, steps: float, training_streak: int) -> list:
        """提取特征向量（含截距）。"""
        return [1.0, workout_intensity, sleep_hours, hr_deviation,
                steps / 10000.0, training_streak]

    def update(self, workout_intensity: float, sleep_hours: float,
               resting_hr: float, resting_hr_baseline: float,
               steps: float, training_days_streak: int,
               observed_recovery: float):
        """用新的观测数据在线更新后验。

        Args:
            workout_intensity: 0-10 训练强度
            sleep_hours: 睡眠小时数
            resting_hr: 今日静息心率
            resting_hr_baseline: 个人基线静息心率
            steps: 昨日步数
            training_days_streak: 连续训练天数
            observed_recovery: 实际恢复分数（0-100）。
                来源：用户自评 RPE、次日训练完成度、或次日静息心率恢复情况。
        """
        x = self._extract_features(workout_intensity, sleep_hours,
                                   resting_hr - resting_hr_baseline,
                                   steps, training_days_streak)
        y = observed_recovery

        self.n += 1
        self.last_update = datetime.now().isoformat()

        # 保存用于诊断
        self.recent_features.append(x)
        self.recent_outcomes.append(y)
        if len(self.recent_features) > 60:
            self.recent_features.pop(0)
            self.recent_outcomes.pop(0)

        # ── 贝叶斯更新（共轭先验闭合公式）──
        # 更新精度矩阵: Λ_n = Λ_{n-1} + x x^T
        for i in range(self.k):
            for j in range(self.k):
                self.Lambda[i][j] += x[i] * x[j]

        # 更新均值: μ_n = Λ_n^{-1} (Λ_{n-1} μ_{n-1} + x y)
        # 由于 Λ_n 是满秩的，我们用增量方式更新
        # 先计算 Λ_{n-1} μ_{n-1}（在更新 Λ 之前保存的值）
        # 这里简化为：用 Sherman-Morrison 公式迭代更新 μ_n 和 Λ_n^{-1}

        # 实际实现：直接求解线性系统（k=6 很小，O(k³)=216 完全可以）
        # 求解 (Λ_n) μ_n = (Λ_n - x x^T) μ_old + x y
        # 但 Λ_n 已经更新了，所以直接解 Λ_n μ_n = b

        # 构造右侧向量 b = Λ_old * μ_old + x * y
        # 其中 Λ_old = Λ_n - x x^T
        b = [0.0] * self.k
        for i in range(self.k):
            b[i] = x[i] * y
            for j in range(self.k):
                # Λ_old[i][j] = Λ_n[i][j] - x[i] * x[j]
                lambda_old_ij = self.Lambda[i][j] - x[i] * x[j]
                b[i] += lambda_old_ij * self.mu[j]

        # 求解 Λ_n μ_n = b（Cholesky 分解，k=6）
        self.mu = _solve_linear_system(self.Lambda, b)

        # 更新 σ² 后验: a_n = a_0 + n/2
        self.a_n = self.a0 + self.n / 2.0
        # b_n = b_0 + 0.5 * (y^T y + μ_0^T Λ_0 μ_0 - μ_n^T Λ_n μ_n)
        mu_lambda_mu = sum(self.mu[i] * sum(self.Lambda[i][j] * self.mu[j]
                                            for j in range(self.k))
                           for i in range(self.k))
        # μ_0^T Λ_0 μ_0 是常数，用初始值近似
        prior_quad = self.prior_precision * sum(w * w for w in self.mu) * 0.5
        self.b_n = self.b0 + 0.5 * (y * y + prior_quad - mu_lambda_mu)
        self.b_n = max(self.b_n, 1.0)  # 保持正数

    def predict(self, workout_intensity: float, sleep_hours: float,
                resting_hr: float, resting_hr_baseline: float,
                steps: float, training_days_streak: int) -> dict:
        """预测恢复分数，带不确定性区间。

        Returns:
            dict with predicted_score, uncertainty, confidence_interval, is_reliable
        """
        x = self._extract_features(workout_intensity, sleep_hours,
                                   resting_hr - resting_hr_baseline,
                                   steps, training_days_streak)

        # 预测均值: ŷ = μ_n^T x
        predicted = sum(self.mu[i] * x[i] for i in range(self.k))

        # 预测方差: σ² * (1 + x^T Λ_n^{-1} x)
        sigma2 = self.b_n / (self.a_n - 1) if self.a_n > 1 else self.b_n / self.a_n
        sigma2 = max(sigma2, 1.0)

        # 计算 x^T Λ_n^{-1} x（通过求解 Λ_n v = x 得到 v = Λ_n^{-1} x）
        v = _solve_linear_system(self.Lambda, x)
        x_inv_x = sum(x[i] * v[i] for i in range(self.k))
        pred_variance = sigma2 * (1.0 + max(x_inv_x, 0.0))
        pred_std = math.sqrt(pred_variance)

        # 95% 置信区间
        ci_lower = max(0, predicted - 1.96 * pred_std)
        ci_upper = min(100, predicted + 1.96 * pred_std)

        # 可靠性：样本越多越可靠
        if self.n < 3:
            reliability = "先验主导（数据不足）"
        elif self.n < 7:
            reliability = "数据积累中"
        elif self.n < 21:
            reliability = "初步个性化"
        else:
            reliability = "充分个性化"

        predicted = max(0, min(100, round(predicted)))

        # 训练建议
        if predicted >= 75:
            action = "train_hard"
            advice = "身体恢复良好，可以进行高强度训练"
        elif predicted >= 55:
            action = "train_moderate"
            advice = "恢复中等，建议中等强度或技术训练"
        elif predicted >= 35:
            action = "train_light"
            advice = "恢复欠佳，建议轻量有氧或拉伸"
        else:
            action = "rest"
            advice = "需要休息！今天做拉伸或彻底休息"

        return {
            "predicted_score": predicted,
            "uncertainty": round(pred_std, 1),
            "confidence_interval": [round(ci_lower), round(ci_upper)],
            "reliability": reliability,
            "samples_used": self.n,
            "action": action,
            "advice": advice,
            "weights": {  # 当前后验权重（可解释性）
                "intercept": round(self.mu[0], 2),
                "workout_intensity": round(self.mu[1], 2),
                "sleep": round(self.mu[2], 2),
                "hr_deviation": round(self.mu[3], 2),
                "steps": round(self.mu[4], 2),
                "training_streak": round(self.mu[5], 2),
            },
        }


# ═══════════════════════════════════════════════════════════════════
# 轻量级线性求解器（避免 numpy 依赖）
# ═══════════════════════════════════════════════════════════════════

def _solve_linear_system(A: list, b: list) -> list:
    """Cholesky 分解求解正定对称线性系统 A x = b。

    纯 Python 实现，k≤6 时 O(216) 操作，零依赖。
    """
    n = len(A)
    # Cholesky: A = L L^T
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                diag = A[i][i] - s
                L[i][j] = math.sqrt(max(diag, 1e-10))
            else:
                L[i][j] = (A[i][j] - s) / max(L[j][j], 1e-10)

    # 前向代入: L y = b
    y = [0.0] * n
    for i in range(n):
        s = sum(L[i][j] * y[j] for j in range(i))
        y[i] = (b[i] - s) / max(L[i][i], 1e-10)

    # 后向代入: L^T x = y
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = sum(L[j][i] * x[j] for j in range(i + 1, n))
        x[i] = (y[i] - s) / max(L[i][i], 1e-10)

    return x


# ═══════════════════════════════════════════════════════════════════
# 观测恢复分数的启发式生成
# ═══════════════════════════════════════════════════════════════════

def estimate_observed_recovery(next_day_resting_hr: float,
                               resting_hr_baseline: float,
                               workout_completed: bool = True,
                               self_reported_feeling: int = None) -> float:
    """从次日数据估算实际恢复分数（0-100），作为贝叶斯更新的目标值。

    在缺少用户自评时，用次日静息心率恢复情况 + 训练完成度
    来估算真实恢复水平。

    Args:
        next_day_resting_hr: 次日静息心率
        resting_hr_baseline: 个人基线静息心率
        workout_completed: 是否完成了计划训练
        self_reported_feeling: 用户自评感受 1-10（可选）

    Returns:
        estimated recovery score (0-100)
    """
    score = 50.0

    # 心率恢复评估（权重最大）
    hr_diff = next_day_resting_hr - resting_hr_baseline
    if hr_diff <= 0:
        score += 25  # 心率完全恢复
    elif hr_diff <= 3:
        score += 15
    elif hr_diff <= 6:
        score += 5
    elif hr_diff <= 10:
        score -= 10
    else:
        score -= 20  # 心率明显偏高

    # 训练完成度
    if workout_completed:
        score += 10
    else:
        score -= 15

    # 自评感受
    if self_reported_feeling is not None:
        score += (self_reported_feeling - 5) * 5

    return max(0, min(100, score))


# ═══════════════════════════════════════════════════════════════════
# 用户模型管理（多用户）
# ═══════════════════════════════════════════════════════════════════

from collections import OrderedDict as _OrderedDict

_user_models = _OrderedDict()  # user_id → BayesianRecoveryModel (LRU, max 200)
_MAX_USER_MODELS = 200


def get_user_model(user_id: int) -> BayesianRecoveryModel:
    """获取或创建用户的贝叶斯恢复模型。"""
    if user_id not in _user_models:
        if len(_user_models) >= _MAX_USER_MODELS:
            _user_models.popitem(last=False)  # 淘汰最久未用的
        _user_models[user_id] = BayesianRecoveryModel()
    else:
        _user_models.move_to_end(user_id)  # 标记最近使用
    return _user_models[user_id]


def invalidate_user_model(user_id: int):
    """用户数据变更时清除该用户的贝叶斯模型（下次请求会从历史数据重建）。"""
    if user_id in _user_models:
        del _user_models[user_id]


def update_user_model(user_id: int, **kwargs) -> dict:
    """更新用户模型并返回个性化预测。"""
    model = get_user_model(user_id)

    observed = estimate_observed_recovery(
        kwargs.get("next_day_resting_hr", kwargs.get("resting_hr", 65)),
        kwargs.get("resting_hr_baseline", 60),
        kwargs.get("workout_completed", True),
        kwargs.get("self_reported_feeling"),
    )

    model.update(
        kwargs.get("workout_intensity", 0),
        kwargs.get("sleep_hours", 7),
        kwargs.get("resting_hr", 65),
        kwargs.get("resting_hr_baseline", 60),
        kwargs.get("steps", 8000),
        kwargs.get("training_days_streak", 0),
        observed,
    )

    prediction = model.predict(
        kwargs.get("workout_intensity", 0),
        kwargs.get("sleep_hours", 7),
        kwargs.get("resting_hr", 65),
        kwargs.get("resting_hr_baseline", 60),
        kwargs.get("steps", 8000),
        kwargs.get("training_days_streak", 0),
    )

    return {
        "recovery": prediction,
        "model_info": {
            "samples_used": model.n,
            "reliability": prediction["reliability"],
            "weights": prediction["weights"],
        },
    }
