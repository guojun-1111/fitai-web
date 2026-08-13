# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""V7.0 Research: SOTA 异常检测基线方法（纯 Python，零依赖）。

实现两种广泛使用的异常检测方法用于论文对比：
1. Isolation Forest (Liu et al., 2008, TKDD) — 基于树的集成异常检测
2. Local Outlier Factor (Breunig et al., 2000, SIGMOD) — 基于密度的局部异常检测

均在 1 核 CPU 上运行，纯 Python 实现，无需 sklearn/numpy。
"""
import math
import random


# ═══════════════════════════════════════════════════════════════════
# Isolation Forest
# ═══════════════════════════════════════════════════════════════════

class IsolationForest:
    """Isolation Forest 异常检测（Liu et al., 2008）。

    原理：异常点更容易被随机分割隔离 → 平均路径长度更短。
    通过构建多棵随机树，用平均路径长度计算异常分数。
    """

    def __init__(self, n_trees: int = 100, sample_size: int = 256,
                 contamination: float = 0.1, random_seed: int = 42):
        self.n_trees = n_trees
        self.sample_size = sample_size
        self.contamination = contamination
        self.rng = random.Random(random_seed)
        self.trees = []

    def fit(self, X: list):
        """训练 Isolation Forest。

        Args:
            X: list of [feature_vector] 或 2D list
        """
        n = len(X)
        if n == 0:
            return self

        height_limit = int(math.ceil(math.log2(max(self.sample_size, 1))))
        self.trees = []

        for _ in range(self.n_trees):
            sample_size = min(self.sample_size, n)
            sample_indices = [self.rng.randint(0, n - 1) for _ in range(sample_size)]
            sample = [(i, X[i]) for i in sample_indices]
            tree = _build_itree(sample, 0, height_limit, self.rng)
            self.trees.append(tree)

        # 计算异常分数的阈值
        self._compute_threshold(X)
        return self

    def predict(self, X: list) -> list:
        """返回每个样本的异常标签（1=异常, 0=正常）。"""
        scores = self.score_samples(X)
        threshold = getattr(self, 'threshold_', 0.5)
        return [1 if s > threshold else 0 for s in scores]

    def score_samples(self, X: list) -> list:
        """返回每个样本的异常分数 [0, 1]，越高越异常。"""
        if not self.trees:
            return [0.5] * len(X)

        scores = []
        for x in X:
            path_sum = 0.0
            for tree in self.trees:
                path_sum += _path_length(x, tree, 0)
            avg_path = path_sum / len(self.trees)
            # 标准化异常分数
            c = _c_factor(self.sample_size)
            score = 2.0 ** (-avg_path / c)
            scores.append(score)
        return scores

    def _compute_threshold(self, X: list):
        scores = sorted(self.score_samples(X), reverse=True)
        cutoff = int(len(scores) * self.contamination)
        self.threshold_ = scores[cutoff] if cutoff < len(scores) else 0.5


def _build_itree(data: list, depth: int, height_limit: int, rng: random.Random) -> dict:
    """递归构建 Isolation Tree。"""
    n = len(data)
    if n <= 1 or depth >= height_limit:
        return {"type": "leaf", "size": n}

    # 随机选特征和分割值
    features = list(range(len(data[0][1])))
    if not features:
        return {"type": "leaf", "size": n}

    feat = rng.choice(features)
    values = [d[1][feat] for d in data]
    min_val, max_val = min(values), max(values)

    if min_val == max_val:
        return {"type": "leaf", "size": n}

    split = rng.uniform(min_val, max_val)
    left = [d for d in data if d[1][feat] < split]
    right = [d for d in data if d[1][feat] >= split]

    if not left or not right:
        return {"type": "leaf", "size": n}

    return {
        "type": "node",
        "feature": feat,
        "split": split,
        "left": _build_itree(left, depth + 1, height_limit, rng),
        "right": _build_itree(right, depth + 1, height_limit, rng),
    }


def _path_length(x: list, tree: dict, depth: int) -> float:
    """计算样本在树中的路径长度。"""
    if tree["type"] == "leaf":
        return depth + _c_factor(tree["size"])
    feat, split = tree["feature"], tree["split"]
    if x[feat] < split:
        return _path_length(x, tree["left"], depth + 1)
    else:
        return _path_length(x, tree["right"], depth + 1)


def _c_factor(n: int) -> float:
    """二叉搜索树平均路径长度的调和数近似。"""
    if n <= 1:
        return 0.0
    if n == 2:
        return 1.0
    return 2.0 * (math.log(n - 1) + 0.5772156649) - (2.0 * (n - 1) / n)


# ═══════════════════════════════════════════════════════════════════
# Local Outlier Factor (LOF)
# ═══════════════════════════════════════════════════════════════════

def compute_lof(X: list, k: int = 5) -> list:
    """Local Outlier Factor (Breunig et al., 2000)。

    对每个点计算局部密度比：LOF = (邻域平均局部可达密度) / (该点局部可达密度)。
    LOF >> 1 表示该点密度显著低于邻居 → 异常。

    Args:
        X: list of [feature_vector]
        k: 邻域大小

    Returns:
        list of LOF scores (越高越异常)
    """
    n = len(X)
    if n < k + 1:
        return [1.0] * n

    # 计算所有点对的 k-距离和 k-邻域
    k_distances = []
    k_neighbors = []

    for i in range(n):
        dists = []
        for j in range(n):
            if i == j:
                continue
            d = _euclidean(X[i], X[j])
            dists.append((d, j))
        dists.sort(key=lambda x: x[0])
        k_dist = dists[k - 1][0] if k - 1 < len(dists) else dists[-1][0]
        k_distances.append(k_dist)
        k_neighbors.append([j for d, j in dists[:k]])

    # 计算局部可达密度
    lrd = []
    for i in range(n):
        reach_sum = 0.0
        for j in k_neighbors[i]:
            # reach-dist_k(i, j) = max(k-distance(j), distance(i, j))
            d_ij = _euclidean(X[i], X[j])
            reach = max(k_distances[j], d_ij)
            reach_sum += reach
        lrd.append(len(k_neighbors[i]) / max(reach_sum, 1e-10))

    # 计算 LOF
    lof_scores = []
    for i in range(n):
        lrd_sum = 0.0
        for j in k_neighbors[i]:
            lrd_sum += lrd[j]
        avg_lrd = lrd_sum / max(len(k_neighbors[i]), 1)
        lof_scores.append(avg_lrd / max(lrd[i], 1e-10))

    return lof_scores


def _euclidean(a: list, b: list) -> float:
    return math.sqrt(sum((ai - bi) ** 2 for ai, bi in zip(a, b)))


# ═══════════════════════════════════════════════════════════════════
# 评估接口（与 evaluation.py 兼容）
# ═══════════════════════════════════════════════════════════════════

def baseline_isolation_forest(metrics_by_date: dict) -> list:
    """Isolation Forest 基线：将每日多指标作为特征向量进行异常检测。

    Args:
        metrics_by_date: {date: {metric: value, ...}, ...}

    Returns:
        list of {"date": str, "method": "isolation_forest"}
    """
    dates = sorted(metrics_by_date.keys())
    if len(dates) < 14:
        return []

    # 构建特征矩阵：每个日期一行，每个指标一列
    all_metrics = set()
    for d in dates:
        for k, v in metrics_by_date[d].items():
            if isinstance(v, (int, float)) and v > 0:
                all_metrics.add(k)
    metric_list = sorted(all_metrics)
    if len(metric_list) < 2:
        return []

    X = []
    valid_dates = []
    for d in dates:
        row = []
        valid = True
        for m in metric_list:
            v = metrics_by_date[d].get(m, 0)
            if v is None or v <= 0:
                row.append(0.0)
            else:
                row.append(float(v))
        X.append(row)
        valid_dates.append(d)

    model = IsolationForest(n_trees=50, sample_size=min(256, len(X)), contamination=0.1)
    model.fit(X)
    scores = model.score_samples(X)
    predictions = model.predict(X)

    anomalies = []
    for i, (date, pred) in enumerate(zip(valid_dates, predictions)):
        if pred == 1:
            anomalies.append({"date": date, "score": round(scores[i], 3),
                              "method": "isolation_forest"})
    return anomalies


def baseline_lof(metrics_by_date: dict, k: int = 5) -> list:
    """LOF 基线：计算每日多指标向量的局部异常因子。

    Args:
        metrics_by_date: {date: {metric: value, ...}, ...}
        k: 邻域大小

    Returns:
        list of {"date": str, "method": "lof"}
    """
    dates = sorted(metrics_by_date.keys())
    if len(dates) < k + 1:
        return []

    all_metrics = set()
    for d in dates:
        for k_, v in metrics_by_date[d].items():
            if isinstance(v, (int, float)) and v > 0:
                all_metrics.add(k_)
    metric_list = sorted(all_metrics)
    if len(metric_list) < 2:
        return []

    X = []
    valid_dates = []
    for d in dates:
        row = []
        for m in metric_list:
            v = metrics_by_date[d].get(m, 0)
            row.append(float(v) if v and v > 0 else 0.0)
        X.append(row)
        valid_dates.append(d)

    lof_scores = compute_lof(X, k)

    # LOF > 2 通常视为异常
    threshold = 2.0
    anomalies = []
    for i, (date, score) in enumerate(zip(valid_dates, lof_scores)):
        if score > threshold:
            anomalies.append({"date": date, "score": round(score, 3), "method": "lof"})
    return anomalies
