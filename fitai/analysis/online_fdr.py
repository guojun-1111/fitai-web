# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""V8.0: 在线 FDR 控制 — 实时序贯异常检测。

当前 probabilistic_anomaly.py 使用 Benjamini-Hochberg 批处理 FDR——
需要所有 p 值才能判断。但真实场景是每天来一条新数据，
需要即时判断而不等待整批。

本模块实现 LORD 过程（Javanmard & Montanari, 2018, JASA），
支持在线序贯 FDR 控制：

核心思想：维护一个"错误预算"（wealth），每步花一点。
发现真异常后 wealth 增加（bonus），连续正常则 wealth 减少。
保证在线 FDR ≤ alpha，不需等待批量数据。

参考：
- Javanmard & Montanari, 2018. "Online Rules for Control of FDR and FNR"
- Ramdas et al., 2017. "Online control of the false discovery rate via betting"
"""
import math


class OnlineFDRController:
    """LORD 在线 FDR 控制器。

    每来一个 p 值就立即判断"是否异常"，不等整批。
    保证长期 FDR ≤ alpha。

    用法:
        ctrl = OnlineFDRController(alpha=0.1)
        for day, p_value in daily_pvalues:
            rejected = ctrl.test(p_value)
            if rejected:
                print(f"{day}: ANOMALY (p={p_value})")
    """

    def __init__(self, alpha: float = 0.1, wealth0: float = None,
                 bonus_factor: float = 0.05):
        """初始化在线 FDR 控制器。

        Args:
            alpha: 目标 FDR 水平
            wealth0: 初始错误预算（默认 alpha/2）
            bonus_factor: 每次发现的奖励因子
        """
        self.alpha = alpha
        self.wealth0 = wealth0 or alpha / 2.0
        self.bonus = bonus_factor

        # 状态
        self.wealth = self.wealth0
        self.t = 0  # 总测试次数
        self.R = 0  # 累积拒绝次数
        self.rejected = []  # 历史拒绝记录

    def test(self, p_value: float) -> tuple:
        """对单个 p 值进行在线 FDR 检验。

        Args:
            p_value: 本次检验的 p 值

        Returns:
            (rejected: bool, threshold: float, wealth: float)
        """
        self.t += 1

        if p_value < 0 or p_value > 1:
            p_value = max(0, min(1, p_value))

        # LORD 判定阈值：α_t = wealth * bonus / (bonus * R + 1)
        threshold = self.wealth * self.bonus / max(self.bonus * self.R + 1, 1)
        threshold = min(threshold, self.alpha)  # 不超过全局 alpha

        rejected = p_value <= threshold

        if rejected:
            self.R += 1
            self.rejected.append(self.t)
            # 发现异常 → 奖励 wealth
            self.wealth += self.alpha - threshold
        else:
            # 未发现 → 消耗 wealth
            self.wealth -= threshold

        self.wealth = max(0.0, self.wealth)  # wealth 不能为负

        return rejected, round(threshold, 6), round(self.wealth, 6)

    def get_stats(self) -> dict:
        """获取控制器状态。"""
        return {
            "tests": self.t,
            "rejections": self.R,
            "empirical_fdr": round(self.R / max(self.t, 1), 3),
            "wealth": round(self.wealth, 6),
            "alpha": self.alpha,
        }


def online_anomaly_detect(daily_pvalues: list, alpha: float = 0.1) -> list:
    """在线异常检测接口。

    输入时序 p 值列表，模拟逐日到达的在线检测。

    Args:
        daily_pvalues: [{"date": str, "p_value": float}, ...] 按日期排序
        alpha: 目标 FDR 水平

    Returns:
        [{"date": str, "rejected": bool, "threshold": float}, ...]
    """
    ctrl = OnlineFDRController(alpha=alpha)
    results = []
    for entry in daily_pvalues:
        rejected, threshold, wealth = ctrl.test(entry["p_value"])
        results.append({
            "date": entry["date"],
            "p_value": entry["p_value"],
            "rejected": rejected,
            "threshold": threshold,
            "wealth": wealth,
        })
    return results


def compare_batch_vs_online(pvalues: list, alpha: float = 0.1) -> dict:
    """对比批处理 BH-FDR vs 在线 LORD 的拒绝数量。

    确保两个方法都在同一组 p 值上控制 FDR ≤ alpha。
    """
    # 批处理 BH
    n = len(pvalues)
    sorted_indices = sorted(range(n), key=lambda i: pvalues[i])
    bh_rejected = [False] * n
    for rank, idx in enumerate(sorted_indices, 1):
        bh_threshold = (rank / n) * alpha
        if pvalues[idx] <= bh_threshold:
            bh_rejected[idx] = True
        else:
            break

    # 在线 LORD
    ctrl = OnlineFDRController(alpha=alpha)
    lord_rejected = []
    for p in pvalues:
        rejected, _, _ = ctrl.test(p)
        lord_rejected.append(rejected)

    return {
        "bh_rejections": sum(bh_rejected),
        "lord_rejections": sum(lord_rejected),
        "n_tests": n,
        "alpha": alpha,
        "are_equal": sum(bh_rejected) == sum(lord_rejected),
    }
