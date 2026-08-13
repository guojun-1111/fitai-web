# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""V9.0: 共形预测 — 分布无关的保证性预测区间。

当前所有预测区间（Bayesian credible interval, CI）都依赖于模型假设正确。
如果模型错了，区间覆盖率的保证就失效了。

共形预测（Conformal Prediction）提供**分布无关**的覆盖保证：
- 只要数据可交换（或近似可交换），区间覆盖概率 ≥ 1-α
- 无论真实分布是什么，这个保证在数学上成立
- 不依赖任何模型假设

两种模式：

1. 分裂共形（离线）：在标定集上计算分位数，对所有新预测使用固定宽度
2. 自适应共形（在线）：α_t = α_{t-1} + γ*(α_target - err_t)
   根据最近覆盖情况动态调整区间宽度
   应对分布漂移（Gibbs & Candes, 2021, JRSS-B）

参考：
- Vovk, V., Gammerman, A., & Shafer, G., 2005. "Algorithmic Learning in a Random World"
- Angelopoulos, A. N., & Bates, S., 2021. "A Gentle Introduction to Conformal Prediction"
- Gibbs, I., & Candes, E., 2021. "Adaptive Conformal Inference Under Distribution Shift", JRSS-B
"""
import math
from collections import deque


class ConformalPredictor:
    """分裂共形预测器。

    离线标定，固定宽度区间。

    用法:
        cp = ConformalPredictor(alpha=0.1)  # 90% 目标覆盖率
        cp.calibrate(y_true_cal, y_pred_cal)
        lo, hi = cp.predict(point_prediction)
    """

    def __init__(self, alpha: float = 0.1):
        """初始化共形预测器。

        Args:
            alpha: 1 - alpha = 目标覆盖率（默认 0.1 → 90% 覆盖）
        """
        self.alpha = alpha
        self.q = None  # 标定分位数
        self._scores = []

    def calibrate(self, y_true: list, y_pred: list):
        """在标定集上拟合非一致性分位数。

        Args:
            y_true: 标定集真实值
            y_pred: 标定集预测值
        """
        n = len(y_true)
        if n < 2:
            self.q = 10.0  # 无数据时用默认宽度
            return

        # 非一致性分数：绝对残差
        scores = [abs(y_true[i] - y_pred[i]) for i in range(n)]
        scores.sort()
        self._scores = scores

        # 有限样本修正：q_idx = ceil((n+1)*(1-alpha)) - 1
        q_idx = min(int(math.ceil((n + 1) * (1 - self.alpha))) - 1, n - 1)
        self.q = max(scores[q_idx], 0.01)

    def predict(self, point_prediction: float) -> tuple:
        """返回共形预测区间。

        Args:
            point_prediction: 模型点预测值

        Returns:
            (lower_bound, upper_bound)
        """
        q = self.q if self.q is not None else 10.0
        return (point_prediction - q, point_prediction + q)

    def evaluate_coverage(self, y_true: list, y_pred: list) -> dict:
        """评估经验覆盖率。

        Returns:
            {coverage, avg_width, n_samples, alpha, valid}
        """
        n = len(y_true)
        if n == 0:
            return {"coverage": 1.0, "avg_width": 0, "n_samples": 0,
                    "alpha": self.alpha, "valid": True}

        covered = 0
        total_width = 0
        for i in range(n):
            lo, hi = self.predict(y_pred[i])
            if lo <= y_true[i] <= hi:
                covered += 1
            total_width += hi - lo

        coverage = covered / n
        return {
            "coverage": round(coverage, 3),
            "avg_width": round(total_width / n, 2),
            "n_samples": n,
            "alpha": self.alpha,
            "valid": coverage >= (1 - self.alpha) - 0.05,  # 允许 5% MC 误差
        }


class AdaptiveConformalPredictor:
    """自适应共形预测器（在线，应对分布漂移）。

    通过在线调整 α 来维持目标覆盖率：
        α_t = α_{t-1} + γ * (α_target - err_t)

    其中 err_t = 1 如果区间未覆盖 y_t，否则 0。
    如果覆盖率过低 → 减小 α → 扩大区间
    如果覆盖率过高 → 增大 α → 缩小区间

    用法:
        acp = AdaptiveConformalPredictor(alpha=0.1, gamma=0.005)
        for y_true, y_pred in stream:
            result = acp.update_and_predict(y_true, y_pred)
            lo, hi = result["lower"], result["upper"]
    """

    def __init__(self, alpha: float = 0.1, gamma: float = 0.005,
                 score_window: int = 100):
        """初始化自适应共形预测器。

        Args:
            alpha: 目标误差率（1-alpha = 目标覆盖率）
            gamma: 学习率，控制 α 的调整速度
            score_window: 存储非一致性分数的窗口大小
        """
        self.alpha_target = alpha
        self.alpha = alpha
        self.gamma = gamma

        self._scores = deque(maxlen=score_window)
        self._coverage_history = deque(maxlen=200)
        self.n_updates = 0
        self.missed = 0

    def update_and_predict(self, y_true: float, y_pred: float) -> dict:
        """在线更新并预测下一个区间。

        注意：返回的区间目标是覆盖**下一个**观测，
        因此使用更新后的 α 和分位数。

        Args:
            y_true: 当前真实值（用于更新 α）
            y_pred: 当前预测值（同时用于更新分数和计算区间）

        Returns:
            {lower, upper, coverage, current_alpha, interval_width, inside}
        """
        self.n_updates += 1

        # 计算非一致性分数
        score = abs(y_true - y_pred)
        self._scores.append(score)

        # 判断当前区间是否覆盖
        if self.n_updates > 1:
            q_current = self._get_quantile(self.alpha)
            lo = y_pred - q_current
            hi = y_pred + q_current
            inside = lo <= y_true <= hi
        else:
            inside = True  # 第一步没有历史区间

        # 更新 α（基于当前覆盖情况）
        err = 0 if inside else 1
        self.alpha += self.gamma * (self.alpha_target - err)
        self.alpha = max(0.01, min(0.5, self.alpha))  # 夹紧

        self._coverage_history.append(inside)
        self.missed += (1 if not inside else 0)

        # 计算下一个区间的分位数
        q_next = self._get_quantile(self.alpha)

        # 返回的是已评估的区间（针对当前观测）
        return {
            "lower": round(y_pred - q_next, 2),
            "upper": round(y_pred + q_next, 2),
            "coverage": round(self._empirical_coverage(), 3),
            "current_alpha": round(self.alpha, 3),
            "interval_width": round(2 * q_next, 2),
            "inside": inside,
        }

    def _get_quantile(self, alpha: float) -> float:
        """从存储的非一致性分数中计算分位数。"""
        if len(self._scores) < 3:
            return 10.0  # 默认宽度
        sorted_scores = sorted(self._scores)
        q_idx = min(int(math.ceil(len(sorted_scores) * (1 - alpha))) - 1,
                    len(sorted_scores) - 1)
        return max(sorted_scores[q_idx], 0.01)

    def _empirical_coverage(self) -> float:
        """计算最近经验覆盖率。"""
        if not self._coverage_history:
            return 1.0
        return sum(self._coverage_history) / len(self._coverage_history)

    def get_coverage_history(self) -> dict:
        """获取覆盖率历史摘要。"""
        n = len(self._coverage_history)
        return {
            "empirical_coverage": round(self._empirical_coverage(), 3),
            "n_observations": self.n_updates,
            "missed_count": self.missed,
            "alpha_current": round(self.alpha, 3),
            "alpha_target": self.alpha_target,
        }


def compare_intervals(bayesian_ci: list, conformal_ci: list,
                      y_true: list) -> dict:
    """比较贝叶斯区间 vs 共形区间。

    Args:
        bayesian_ci: [(lo, hi), ...] 贝叶斯可信区间
        conformal_ci: [(lo, hi), ...] 共形预测区间
        y_true: 真实值列表

    Returns:
        {bayesian: {coverage, avg_width}, conformal: {coverage, avg_width}, winner}
    """
    n = len(y_true)

    def _eval(intervals):
        covered = sum(1 for i in range(n)
                      if intervals[i][0] <= y_true[i] <= intervals[i][1])
        width = sum(intervals[i][1] - intervals[i][0] for i in range(n))
        return {
            "coverage": round(covered / n, 3) if n > 0 else 1.0,
            "avg_width": round(width / n, 2) if n > 0 else 0,
        }

    bayes_eval = _eval(bayesian_ci)
    conf_eval = _eval(conformal_ci)

    # 赢家：覆盖率达标的前提下更窄的区间胜出
    bayes_ok = bayes_eval["coverage"] >= 0.85
    conf_ok = conf_eval["coverage"] >= 0.85

    if bayes_ok and conf_ok:
        winner = "bayesian" if bayes_eval["avg_width"] < conf_eval["avg_width"] else "conformal"
    elif bayes_ok:
        winner = "bayesian"
    elif conf_ok:
        winner = "conformal"
    else:
        winner = "neither"

    return {
        "bayesian": bayes_eval,
        "conformal": conf_eval,
        "winner": winner,
        "n_samples": n,
    }
