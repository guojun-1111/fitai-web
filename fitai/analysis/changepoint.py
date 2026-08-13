# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""V9.0: 贝叶斯变点检测 — 区分"异常一天"和"身体真的变了"。

当前 anomaly 检测（probabilistic_anomaly.py, advanced.py）回答：
"今天的指标是不是不正常？"—— 检测单日离群点。

本模块回答更关键的问题：
"用户的生理基线是不是发生了持久性偏移？"—— 检测状态转换。

两个核心方法：

1. 自适应 CUSUM：累计标准化预测误差，当累积和超过阈值时告警。
   S_t = max(0, S_{t-1} + z_t - drift)
   其中 z_t = (y_obs - y_pred) / y_std

2. 贝叶斯因子：比较"数据来自近期模型"vs"数据来自长期基线"的证据比。
   BF_t = P(y_t | 近期窗口模型) / P(y_t | 长期基线模型)
   累积 log BF < -3 为决定性证据（Kass & Raftery, 1995）。

两种方法互补：CUSUM 对持续漂移敏感，Bayes Factor 对突变敏感。

应用场景：
- 检测过度训练综合征发生前的生理漂移
- 识别训练计划开始/停止产生效果的时间点
- 发现伤病恢复期的结束（回归正常基线）

参考：
- Adams & MacKay, 2007. "Bayesian Online Changepoint Detection", arXiv:0710.3742
- Fearnhead & Liu, 2007. "On-line inference for multiple changepoint problems", JRSS-B
- Lucas, 1982. "Combined Shewhart-CUSUM quality control schemes"
- Kass & Raftery, 1995. "Bayes Factors", JASA
"""
import math
from collections import deque


class BayesianChangePointDetector:
    """贝叶斯变点检测器：CUSUM + Bayes Factor 双轨检测。

    用法:
        detector = BayesianChangePointDetector()
        for day_data in daily_stream:
            result = detector.update(y_obs, y_pred, y_std)
            if result["is_changepoint"]:
                print(f"检测到变点: {result['evidence']} 证据")
    """

    def __init__(self, cusum_threshold: float = 5.0, drift: float = 0.2,
                 window: int = 14, hazard_rate: float = 0.01):
        """初始化检测器。

        Args:
            cusum_threshold: CUSUM 告警阈值（默认 5.0，标准质量控制值）
            drift: CUSUM 漂移参数，每步减去防止慢漂误报
            window: 近期窗口大小（用于 Bayes Factor 的"近期模型"）
            hazard_rate: 先验变点概率（默认 1/100 天）
        """
        self.cusum_threshold = cusum_threshold
        self.drift = drift
        self.window = window
        self.hazard_rate = hazard_rate

        self.cusum_pos = 0.0  # 正向 CUSUM（观测 > 预测）
        self.cusum_neg = 0.0  # 负向 CUSUM（观测 < 预测）
        self.n_updates = 0
        self.log_bf = 0.0  # 累积 log Bayes Factor

        # 基线统计（长窗口 EWMA）
        self.baseline_mean = None
        self.baseline_var = None
        self.baseline_n = 0

        # 近期窗口（环形缓冲）
        self._recent = deque(maxlen=window)

        # 检测历史
        self.changepoints = []
        self._steps_since_reset = 0

    def update(self, observation: float, predictive_mean: float,
               predictive_std: float) -> dict:
        """处理一个新观测。

        Args:
            observation: 实际观测值 y_t
            predictive_mean: 模型预测均值 μ_t
            predictive_std: 模型预测标准差 σ_t

        Returns:
            {cusum_pos, cusum_neg, log_bayes_factor, z_score, is_changepoint,
             direction, evidence, baseline_mean, baseline_std}
        """
        self.n_updates += 1
        self._steps_since_reset += 1

        # ── 标准化预测误差 ──
        pred_std = max(predictive_std, 0.01)
        z = (observation - predictive_mean) / pred_std

        # ── CUSUM 更新 ──
        self.cusum_pos = max(0.0, self.cusum_pos + z - self.drift)
        self.cusum_neg = max(0.0, self.cusum_neg - z - self.drift)

        # ── 基线更新（EWMA）──
        if self.baseline_mean is None:
            self.baseline_mean = observation
            self.baseline_var = pred_std ** 2
            self.baseline_n = 1
        else:
            alpha = 0.05
            self.baseline_mean = alpha * observation + (1 - alpha) * self.baseline_mean
            delta = observation - self.baseline_mean
            self.baseline_var = alpha * delta ** 2 + (1 - alpha) * self.baseline_var
            self.baseline_n += 1

        baseline_std = math.sqrt(max(self.baseline_var, 0.01))

        # ── Bayes Factor：比较观测在预测模型 vs 宽参考模型下的似然 ──
        # H0 (no change): obs ~ StudentT(df=baseline_n, mu=baseline_mean, sigma=baseline_std)
        # H1 (change): obs ~ StudentT(df=1, mu=baseline_mean, sigma=50) 宽参考
        ll_baseline = _student_t_logpdf(observation, df=max(self.baseline_n - 1, 1),
                                        mu=self.baseline_mean, sigma=baseline_std)
        ll_reference = _student_t_logpdf(observation, df=1,
                                         mu=self.baseline_mean, sigma=50.0)
        self.log_bf += ll_reference - ll_baseline
        # log_bf 增加 = 基线模型无法解释观测 = 变点证据

        # ── 判定 ──
        cusum_max = max(self.cusum_pos, self.cusum_neg)
        is_changepoint = cusum_max > self.cusum_threshold

        # Bayes Factor 辅助：log_bf > ln(20) = 强变点证据
        if self.log_bf > math.log(20.0) and self._steps_since_reset >= 5:
            is_changepoint = True

        if self.cusum_neg > self.cusum_pos:
            direction = "degrading"
        elif self.cusum_pos > self.cusum_neg:
            direction = "improving"
        else:
            direction = "stable"

        if self.log_bf > math.log(20.0):
            evidence = "strong_change"
        elif self.log_bf > math.log(3.0):
            evidence = "moderate_change"
        elif self.log_bf < math.log(1.0 / 3.0):
            evidence = "strong_no_change"
        else:
            evidence = "weak"

        if is_changepoint and self._steps_since_reset >= 3:
            self.changepoints.append({
                "step": self.n_updates,
                "direction": direction,
                "cusum_value": round(cusum_max, 3),
                "log_bf": round(self.log_bf, 3),
                "evidence": evidence,
                "z_score": round(z, 3),
            })
            self._reset()

        return {
            "cusum_pos": round(self.cusum_pos, 3),
            "cusum_neg": round(self.cusum_neg, 3),
            "log_bayes_factor": round(self.log_bf, 3),
            "z_score": round(z, 3),
            "is_changepoint": is_changepoint,
            "direction": direction,
            "evidence": evidence,
            "baseline_mean": round(self.baseline_mean, 2),
            "baseline_std": round(baseline_std, 2),
            "n_updates": self.n_updates,
        }

    def _reset(self):
        """变点检测后重置 CUSUM 和近期窗口。"""
        self.cusum_pos = 0.0
        self.cusum_neg = 0.0
        self._recent.clear()
        self._steps_since_reset = 0

    def get_state(self) -> dict:
        """获取检测器完整状态。"""
        return {
            "n_updates": self.n_updates,
            "cusum_pos": self.cusum_pos,
            "cusum_neg": self.cusum_neg,
            "log_bayes_factor": self.log_bf,
            "baseline_mean": self.baseline_mean,
            "baseline_std": math.sqrt(max(self.baseline_var or 0.01, 0.01)),
            "changepoints": len(self.changepoints),
            "steps_since_reset": self._steps_since_reset,
        }


class PhysiologicalShiftDetector:
    """生理状态漂移检测器（应用层封装）。

    连接到 BayesianRecoveryModel，自动获取预测分布，
    检测具体的生理状态改变类型。

    用法:
        detector = PhysiologicalShiftDetector(user_id=1, recovery_model=model)
        result = detector.update({"workout_intensity": 0.6, "sleep_hours": 7.5, ...})
        if result["shift_detected"]:
            print(result["description"])
    """

    def __init__(self, user_id: int, bayesian_recovery_model=None):
        """初始化生理漂移检测器。

        Args:
            user_id: 用户 ID
            bayesian_recovery_model: BayesianRecoveryModel 实例
        """
        self.user_id = user_id
        self.recovery_model = bayesian_recovery_model
        self.detector = BayesianChangePointDetector()
        self.recent_drift = []  # 最近检测到的漂移记录

    def update(self, daily_data: dict) -> dict:
        """处理一天的生理数据。

        Args:
            daily_data: {workout_intensity, sleep_hours, resting_hr,
                          resting_hr_baseline, steps, training_days_streak}

        Returns:
            {shift_detected, shift_type, confidence, description, detector_state}
        """
        if self.recovery_model is None:
            return {"shift_detected": False, "error": "无恢复模型"}

        # 获取模型预测
        pred = self.recovery_model.predict(**daily_data)
        pred_score = pred["predicted_score"]
        pred_std = pred.get("uncertainty", 10.0)

        # 估计观测恢复分数（使用模型内部方法或简单估算）
        observed = daily_data.get("observed_recovery", None)
        if observed is None:
            observed = pred_score  # 无观测时用预测值（不触发变点）

        result = self.detector.update(observed, pred_score, pred_std)

        shift_detected = result["is_changepoint"]
        shift_type = "none"
        description = ""

        if shift_detected:
            if result["direction"] == "degrading":
                shift_type = "overtraining_onset"
                description = (
                    f"恢复分数持续低于预测（CUSUM={result['cusum_pos']}），"
                    f"可能为过度训练早期信号。建议减少训练负荷 30-50% 并增加睡眠。"
                )
            else:
                shift_type = "recovery_breakthrough"
                description = (
                    f"恢复分数持续高于预测（CUSUM={result['cusum_neg']}），"
                    f"可能已适应当前训练负荷。可考虑渐进增加训练量 10%。"
                )
            self.recent_drift.append({
                "date": daily_data.get("date", ""),
                "type": shift_type,
                "description": description,
            })

        return {
            "shift_detected": shift_detected,
            "shift_type": shift_type,
            "confidence": "高" if result["evidence"] == "strong_change" else "中",
            "description": description,
            "detector_state": {
                "cusum_pos": result["cusum_pos"],
                "cusum_neg": result["cusum_neg"],
                "log_bayes_factor": result["log_bayes_factor"],
                "z_score": result["z_score"],
                "n_updates": result["n_updates"],
            },
        }


def detect_physiological_shifts(dates: list, observed: list,
                                predicted: list, stds: list) -> list:
    """批量检测生理状态变点。

    在完整时间序列上运行检测器，返回所有检测到的变点。

    Args:
        dates: 日期字符串列表
        observed: 观测值列表
        predicted: 预测均值列表
        stds: 预测标准差列表

    Returns:
        [{date, shift_type, cusum_value, evidence, direction}]
    """
    detector = BayesianChangePointDetector()
    shifts = []
    for i in range(len(dates)):
        result = detector.update(observed[i], predicted[i], max(stds[i], 0.01))
        if result["is_changepoint"]:
            shifts.append({
                "date": dates[i],
                "shift_type": "degrading" if result["direction"] == "degrading" else "improving",
                "cusum_value": max(result["cusum_pos"], result["cusum_neg"]),
                "log_bayes_factor": result["log_bayes_factor"],
                "evidence": result["evidence"],
                "direction": result["direction"],
            })
    return shifts


def _student_t_logpdf(x: float, df: float, mu: float = 0.0,
                      sigma: float = 1.0) -> float:
    """Student's t 分布的对数概率密度。

    用于 Bayes Factor 计算的似然函数。
    """
    sigma = max(sigma, 1e-10)
    df = max(df, 1.0)
    z = (x - mu) / sigma
    log_kernel = -(df + 1) / 2 * math.log(1 + z * z / df)
    log_norm = (math.lgamma((df + 1) / 2) - math.lgamma(df / 2)
                - 0.5 * math.log(df * math.pi) - math.log(sigma))
    return log_norm + log_kernel
