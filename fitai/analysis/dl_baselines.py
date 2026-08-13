# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""V7.0 Research: 深度学习基线方法（纯 Python，零依赖）。

实现两种神经网络基线用于论文 SOTA 对比：
1. PCA 重构误差 — 线性自编码器的闭式解（等价于 1 层线性 AE）
2. 2 层神经网络自编码器 — 手动反向传播实现

均在 1 核 CPU 上运行，纯 Python，无 PyTorch/TensorFlow 依赖。
"""
import math
import random


# ═══════════════════════════════════════════════════════════════════
# PCA 重构误差基线
# ═══════════════════════════════════════════════════════════════════

def pca_reconstruction_error(X: list, n_components: int = 2) -> list:
    """PCA 重构误差异常检测。

    用前 n_components 个主成分重构数据，重构误差大的点为异常。
    PCA 等价于线性自编码器的最优解。

    Args:
        X: list of [feature_vector] (n_samples × n_features)
        n_components: 保留的主成分数

    Returns:
        list of reconstruction errors (越高越异常)
    """
    n = len(X)
    if n == 0:
        return []
    d = len(X[0])

    # ── 数据中心化 ──
    means = [0.0] * d
    for x in X:
        for j in range(d):
            means[j] += x[j] / n
    X_centered = [[X[i][j] - means[j] for j in range(d)] for i in range(n)]

    # ── 协方差矩阵 ──
    cov = [[0.0] * d for _ in range(d)]
    for i in range(n):
        for j in range(d):
            for k in range(d):
                cov[j][k] += X_centered[i][j] * X_centered[i][k] / (n - 1) if n > 1 else 0

    # ── 幂迭代求前 n_components 个特征向量 ──
    eigenvectors = _power_iteration_top_k(cov, n_components)

    # ── 投影和重构 ──
    errors = []
    for x in X:
        x_ctr = [x[j] - means[j] for j in range(d)]
        # 投影到主成分空间
        projection = [0.0] * n_components
        for p in range(n_components):
            for j in range(d):
                projection[p] += x_ctr[j] * eigenvectors[p][j]
        # 从主成分空间重构
        reconstructed = [0.0] * d
        for p in range(n_components):
            for j in range(d):
                reconstructed[j] += projection[p] * eigenvectors[p][j]
        # 加回均值
        for j in range(d):
            reconstructed[j] += means[j]
        # 重构误差
        err = math.sqrt(sum((x[j] - reconstructed[j]) ** 2 for j in range(d)))
        errors.append(err)

    return errors


def _power_iteration_top_k(A: list, k: int, n_iter: int = 50) -> list:
    """幂迭代 + 紧缩求前 k 个特征向量。"""
    d = len(A)
    k = min(k, d)
    eigenvectors = []
    residual = [[A[i][j] for j in range(d)] for i in range(d)]

    for _ in range(k):
        # 随机初始化
        v = [random.gauss(0, 1) for _ in range(d)]
        for __ in range(n_iter):
            # v = A * v
            Av = [sum(residual[i][j] * v[j] for j in range(d)) for i in range(d)]
            norm = math.sqrt(sum(x * x for x in Av))
            if norm < 1e-12:
                break
            v = [x / norm for x in Av]
        eigenvectors.append(v)
        # 紧缩：A' = A - λ v v^T
        eigenval = sum(v[i] * sum(residual[i][j] * v[j] for j in range(d)) for i in range(d))
        for i in range(d):
            for j in range(d):
                residual[i][j] -= eigenval * v[i] * v[j]

    return eigenvectors


# ═══════════════════════════════════════════════════════════════════
# 2 层神经网络自编码器
# ═══════════════════════════════════════════════════════════════════

class SimpleAutoencoder:
    """2 层全连接自编码器（纯 Python）。

    结构: input → hidden(ReLU) → bottleneck → hidden(ReLU) → output
    用重构误差（MSE）作为异常分数。

    参考: Sakurada & Yairi, 2014 — "Anomaly Detection Using Autoencoders"
    """

    def __init__(self, input_dim: int, hidden_dim: int = 8, bottleneck_dim: int = 3,
                 learning_rate: float = 0.001, random_seed: int = 42):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.bottleneck_dim = bottleneck_dim
        self.lr = learning_rate
        self.rng = random.Random(random_seed)

        # He 初始化
        scale1 = math.sqrt(2.0 / input_dim)
        scale2 = math.sqrt(2.0 / hidden_dim)
        scale3 = math.sqrt(2.0 / bottleneck_dim)
        scale4 = math.sqrt(2.0 / hidden_dim)

        self.W1 = [[self.rng.gauss(0, scale1) for _ in range(input_dim)] for __ in range(hidden_dim)]
        self.b1 = [0.0] * hidden_dim
        self.W2 = [[self.rng.gauss(0, scale2) for _ in range(hidden_dim)] for __ in range(bottleneck_dim)]
        self.b2 = [0.0] * bottleneck_dim
        self.W3 = [[self.rng.gauss(0, scale3) for _ in range(bottleneck_dim)] for __ in range(hidden_dim)]
        self.b3 = [0.0] * hidden_dim
        self.W4 = [[self.rng.gauss(0, scale4) for _ in range(hidden_dim)] for __ in range(input_dim)]
        self.b4 = [0.0] * input_dim

    def _forward(self, x: list) -> tuple:
        """前向传播。"""
        # Encoder: input → hidden1
        h1 = [max(0, sum(self.W1[i][j] * x[j] for j in range(self.input_dim)) + self.b1[i])
              for i in range(self.hidden_dim)]
        # Bottleneck
        z = [sum(self.W2[i][j] * h1[j] for j in range(self.hidden_dim)) + self.b2[i]
             for i in range(self.bottleneck_dim)]
        # Decoder: bottleneck → hidden2
        h2 = [max(0, sum(self.W3[i][j] * z[j] for j in range(self.bottleneck_dim)) + self.b3[i])
              for i in range(self.hidden_dim)]
        # Output
        out = [sum(self.W4[i][j] * h2[j] for j in range(self.hidden_dim)) + self.b4[i]
               for i in range(self.input_dim)]
        return out, h1, z, h2

    def train_step(self, x: list) -> float:
        """单样本 SGD + 手动反向传播。"""
        out, h1, z, h2 = self._forward(x)

        # MSE loss + gradient
        loss = sum((out[i] - x[i]) ** 2 for i in range(self.input_dim)) / self.input_dim
        dout = [2.0 * (out[i] - x[i]) / self.input_dim for i in range(self.input_dim)]

        # W4, b4 梯度
        dW4 = [[0.0] * self.hidden_dim for _ in range(self.input_dim)]
        db4 = [0.0] * self.input_dim
        for i in range(self.input_dim):
            db4[i] = dout[i]
            for j in range(self.hidden_dim):
                dW4[i][j] = dout[i] * h2[j]

        # h2 梯度（ReLU backward）
        dh2 = [0.0] * self.hidden_dim
        for j in range(self.hidden_dim):
            for i in range(self.input_dim):
                dh2[j] += dout[i] * self.W4[i][j]
            if h2[j] <= 0:
                dh2[j] = 0

        # W3, b3 梯度
        dW3 = [[0.0] * self.bottleneck_dim for _ in range(self.hidden_dim)]
        db3 = [0.0] * self.hidden_dim
        for i in range(self.hidden_dim):
            db3[i] = dh2[i]
            for j in range(self.bottleneck_dim):
                dW3[i][j] = dh2[i] * z[j]

        # z 梯度
        dz = [0.0] * self.bottleneck_dim
        for j in range(self.bottleneck_dim):
            for i in range(self.hidden_dim):
                dz[j] += dh2[i] * self.W3[i][j]

        # h1 梯度（ReLU backward）
        dh1 = [0.0] * self.hidden_dim
        for j in range(self.hidden_dim):
            for i in range(self.bottleneck_dim):
                dh1[j] += dz[i] * self.W2[i][j]
            if h1[j] <= 0:
                dh1[j] = 0

        # W1, b1 梯度
        dW1 = [[0.0] * self.input_dim for _ in range(self.hidden_dim)]
        db1 = [0.0] * self.hidden_dim
        for i in range(self.hidden_dim):
            db1[i] = dh1[i]
            for j in range(self.input_dim):
                dW1[i][j] = dh1[i] * x[j]

        # W2, b2 梯度
        dW2 = [[0.0] * self.hidden_dim for _ in range(self.bottleneck_dim)]
        db2 = [0.0] * self.bottleneck_dim
        for i in range(self.bottleneck_dim):
            db2[i] = dz[i]
            for j in range(self.hidden_dim):
                dW2[i][j] = dz[i] * h1[j]

        # SGD 更新
        for i in range(self.hidden_dim):
            for j in range(self.input_dim):
                self.W1[i][j] -= self.lr * dW1[i][j]
            self.b1[i] -= self.lr * db1[i]
        for i in range(self.bottleneck_dim):
            for j in range(self.hidden_dim):
                self.W2[i][j] -= self.lr * dW2[i][j]
            self.b2[i] -= self.lr * db2[i]
        for i in range(self.hidden_dim):
            for j in range(self.bottleneck_dim):
                self.W3[i][j] -= self.lr * dW3[i][j]
            self.b3[i] -= self.lr * db3[i]
        for i in range(self.input_dim):
            for j in range(self.hidden_dim):
                self.W4[i][j] -= self.lr * dW4[i][j]
            self.b4[i] -= self.lr * db4[i]

        return loss

    def score_samples(self, X: list) -> list:
        """返回每个样本的重构误差。"""
        errors = []
        for x in X:
            out, _, _, _ = self._forward(x)
            err = math.sqrt(sum((out[i] - x[i]) ** 2 for i in range(self.input_dim)))
            errors.append(err)
        return errors


def baseline_pca(daily_metrics: dict) -> list:
    """PCA 重构误差基线。"""
    return _dl_baseline_wrapper(daily_metrics, method="pca")


def baseline_autoencoder(daily_metrics: dict, epochs: int = 30) -> list:
    """自编码器重构误差基线。"""
    return _dl_baseline_wrapper(daily_metrics, method="autoencoder", epochs=epochs)


def _dl_baseline_wrapper(metrics_by_date: dict, method: str = "pca",
                          epochs: int = 30) -> list:
    """将 DL 基线包装为与 evaluation.py 兼容的格式。"""
    dates = sorted(metrics_by_date.keys())
    if len(dates) < 14:
        return []

    all_metrics = sorted(set(k for d in dates for k, v in metrics_by_date[d].items()
                             if isinstance(v, (int, float)) and v > 0))
    if len(all_metrics) < 2:
        return []

    X, valid_dates = [], []
    for d in dates:
        row = [float(metrics_by_date[d].get(m, 0) or 0) for m in all_metrics]
        X.append(row)
        valid_dates.append(d)

    # 归一化
    n, d = len(X), len(X[0])
    means = [sum(X[i][j] for i in range(n)) / n for j in range(d)]
    stds = [math.sqrt(sum((X[i][j] - means[j]) ** 2 for i in range(n)) / n) for j in range(d)]
    X_norm = [[(X[i][j] - means[j]) / max(stds[j], 1e-10) for j in range(d)] for i in range(n)]

    if method == "pca":
        errors = pca_reconstruction_error(X_norm, n_components=2)
    else:
        model = SimpleAutoencoder(d, hidden_dim=8, bottleneck_dim=3)
        for epoch in range(epochs):
            total_loss = 0.0
            for x in X_norm:
                total_loss += model.train_step(x)
        errors = model.score_samples(X_norm)

    # 阈值：均值 + 2σ
    mean_err = sum(errors) / len(errors)
    std_err = math.sqrt(sum((e - mean_err) ** 2 for e in errors) / len(errors))
    threshold = mean_err + 2.0 * std_err

    anomalies = []
    for i, (date, err) in enumerate(zip(valid_dates, errors)):
        if err > threshold:
            anomalies.append({"date": date, "score": round(err, 3), "method": method})
    return anomalies
