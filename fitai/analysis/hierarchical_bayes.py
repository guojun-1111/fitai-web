# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""V8.0: 层次贝叶斯恢复模型 — 多用户部分池化（Partial Pooling）。

这是 fitai-web 最具护城河的算法升级。当前 bayesian_recovery.py 中
每个用户独立训练——冷启动时靠先验，数据多了靠后验，但不同用户之间
零共享。

层次贝叶斯的核心洞察：
- 从所有用户学习人口级先验分布
- 新用户立即继承人口级知识（无需冷启动）
- 老用户的数据同时优化个人后验和人口分布
- 用户越多 → 人口先验越准 → 所有用户受益

方法：
  Level 1 (Population):  μ_pop, Σ_pop ← 所有用户后验的元分析
  Level 2 (Individual):  μ_user ~ N(μ_pop, τ²I) + 个人数据 → 后验

这种层次结构意味着：
1. 单用户模型（当前）  → RMSE 受限于该用户的数据量
2. 固定权重（市场方案）→ RMSE 受限于人群平均的粗糙度
3. 层次贝叶斯（本方案）→ RMSE 随用户数和每用户数据量同时下降
   → 竞争对手无法复制，除非他们也积累多用户数据

参考：
- Gelman et al., 2013. "Bayesian Data Analysis" (3rd ed.), Ch.5
- Efron & Morris, 1975. "Data Analysis Using Stein's Estimator"
"""
import math
from collections import defaultdict, OrderedDict as _OrderedDict


class HierarchicalBayesianModel:
    """层次贝叶斯恢复评分模型。

    两层结构：
    - 人口层：所有用户共享的全局先验
    - 个体层：每个用户个性化的后验

    新用户自动继承人口先验，老用户享有个性化后验。
    """

    def __init__(self, k: int = 6, tau2: float = 25.0):
        """初始化层次模型。

        Args:
            k: 特征维度
            tau2: 层间方差 τ²（控制个体偏离人口先验的程度）
                  小值 = 个体更接近人口均值（强收缩）
                  大值 = 个体更独立（弱收缩）
        """
        self.k = k
        self.tau2 = tau2  # 层间方差

        # 人口层超参数（所有用户共享）
        self.mu_pop = [60.0, -2.0, 1.5, -1.0, 0.0005, -1.5]  # 人口均值
        self.Lambda_pop = [[1.0 if i == j else 0.0 for j in range(k)] for i in range(k)]  # 人口精度

        # 人口层的共轭超参数（Normal-Wishart）
        self.nu0 = k + 2  # Wishart 自由度
        self.W0 = [[1.0 if i == j else 0.0 for j in range(k)] for i in range(k)]  # Wishart 尺度矩阵

        # 个体层：每个用户的独立后验（LRU，最大 500 用户）
        self.users = _OrderedDict()
        self._MAX_USERS = 500
        self.total_updates = 0

    def initialize_user(self, user_id: int):
        """为新用户初始化个体层（从人口先验继承）。"""
        if user_id not in self.users:
            if len(self.users) >= self._MAX_USERS:
                self.users.popitem(last=False)  # 淘汰最久未用的
            self.users[user_id] = {
                "mu": list(self.mu_pop),
                "Lambda": [[self.Lambda_pop[i][j] / self.tau2 for j in range(self.k)]
                           for i in range(self.k)],
                "n": 0,
                "a_n": 3.0,
                "b_n": 100.0,
            }
        else:
            self.users.move_to_end(user_id)

    def update_user(self, user_id: int, features: list, observed: float):
        """用单日数据更新个体后验 + 累积人口层统计量。

        Args:
            user_id: 用户 ID
            features: [x0, x1, ..., x5] 特征向量（含截距 1.0）
            observed: 观测恢复分数 (0-100)
        """
        self.initialize_user(user_id)
        u = self.users[user_id]

        x = list(features)
        y = observed

        # ── 个体层更新（带人口先验收缩）──
        # 先验精度矩阵 = Lambda_pop / tau²（人口先验 + 收缩因子）
        prior_precision = self.tau2

        # Lambda_n = Lambda_{n-1} + x x^T
        for i in range(self.k):
            for j in range(self.k):
                u["Lambda"][i][j] += x[i] * x[j]

        # 构造 b = Lambda_old * mu_old + x * y
        b = [0.0] * self.k
        for i in range(self.k):
            b[i] = x[i] * y
            for j in range(self.k):
                lambda_old_ij = u["Lambda"][i][j] - x[i] * x[j]
                b[i] += lambda_old_ij * u["mu"][j]
            # 加入人口先验的收缩力
            b[i] += prior_precision * self.mu_pop[i]

        u["mu"] = _solve_cholesky(u["Lambda"], b)
        u["n"] += 1

        # 更新 sigma² 后验
        u["a_n"] = 3.0 + u["n"] / 2.0
        residual2 = (y - sum(u["mu"][i] * x[i] for i in range(self.k))) ** 2
        u["b_n"] = max(100.0 + 0.5 * residual2, 1.0)

        self.total_updates += 1

        # ── 定期更新人口先验（每 50 次总体更新）──
        if self.total_updates % 50 == 0:
            self._update_population_prior()

    def predict(self, user_id: int, features: list) -> dict:
        """对特定用户预测恢复分数。

        如果用户不存在，用人口先验预测（冷启动）。
        """
        x = list(features)
        self.initialize_user(user_id)
        u = self.users[user_id]

        if u["n"] < 3:
            # 冷启动：用人口先验
            predicted = sum(self.mu_pop[i] * x[i] for i in range(self.k))
            ci_width = 20  # 人口先验的高不确定性
        else:
            predicted = sum(u["mu"][i] * x[i] for i in range(self.k))
            sigma2 = u["b_n"] / max(u["a_n"] - 1, 1)
            v = _solve_cholesky(u["Lambda"], x)
            x_inv_x = sum(x[i] * v[i] for i in range(self.k))
            ci_width = 1.96 * math.sqrt(sigma2 * (1.0 + max(x_inv_x, 0.0)))

        predicted = max(0, min(100, round(predicted)))
        ci_lower = max(0, round(predicted - ci_width))
        ci_upper = min(100, round(predicted + ci_width))
        n_users = len(self.users)

        if u["n"] < 3:
            reliability = f"冷启动（继承 {n_users} 用户人口先验）"
        elif u["n"] < 7:
            reliability = "数据积累中"
        elif u["n"] < 21:
            reliability = "初步个性化"
        else:
            reliability = f"充分个性化（参考 {n_users} 用户人群）"

        return {
            "predicted_score": predicted,
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
            "samples_used": u["n"],
            "total_users": n_users,
            "reliability": reliability,
            "is_cold_start": u["n"] < 3,
        }

    def _update_population_prior(self):
        """从所有用户后验更新人口先验（经验贝叶斯）。"""
        if not self.users:
            return

        k = self.k
        # 收集所有用户后验均值的加权平均（按样本量加权）
        total_n = 0
        weighted_sum = [0.0] * k

        for uid, u in self.users.items():
            if u["n"] < 1:
                continue
            w = u["n"]
            total_n += w
            for i in range(k):
                weighted_sum[i] += w * u["mu"][i]

        if total_n > 0:
            for i in range(k):
                self.mu_pop[i] = weighted_sum[i] / total_n

        # 更新层间方差 τ²（个体偏离人口均值的程度）
        if len(self.users) >= 2:
            ss = 0.0
            count = 0
            for uid, u in self.users.items():
                if u["n"] < 3:
                    continue
                for i in range(k):
                    ss += (u["mu"][i] - self.mu_pop[i]) ** 2
                    count += 1
            if count > 0:
                self.tau2 = max(1.0, ss / count)


# ═══════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════

def _solve_cholesky(A: list, b: list) -> list:
    n = len(A)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(L[i][k] * L[j][k] for k in range(j))
            val = A[i][j] - s
            if i == j:
                L[i][j] = math.sqrt(max(val, 1e-10))
            else:
                L[i][j] = val / max(L[j][j], 1e-10)
    y = [0.0] * n
    for i in range(n):
        s = sum(L[i][j] * y[j] for j in range(i))
        y[i] = (b[i] - s) / max(L[i][i], 1e-10)
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = sum(L[j][i] * x[j] for j in range(i + 1, n))
        x[i] = (y[i] - s) / max(L[i][i], 1e-10)
    return x
