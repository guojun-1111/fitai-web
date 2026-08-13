# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""V7.0 提取: 轻量级 TTL 内存缓存（OrderedDict 实现 O(1) LRU 淘汰）。

从 server.py 提取为独立模块，便于测试和复用。
"""
import threading
import time as _time
from collections import OrderedDict


class TTLCache:
    """线程安全的 TTL 缓存，基于 OrderedDict 实现 O(1) LRU 淘汰。

    用法:
        cache = TTLCache(max_size=500, evict_batch=100, default_ttl=180)
        cache.set("key", value)
        value = cache.get("key")  # 过期返回 None
        cache.invalidate_user(prefix)  # 清除匹配前缀的所有键
    """

    def __init__(self, max_size: int = 500, evict_batch: int = 100,
                 default_ttl: int = 180):
        self._store = OrderedDict()
        self._lock = threading.Lock()
        self.max_size = max_size
        self.evict_batch = evict_batch
        self.default_ttl = default_ttl

    def get(self, key: str, ttl: int = None) -> object:
        """获取缓存值，过期返回 None。访问时刷新 LRU 位置。"""
        with self._lock:
            if key not in self._store:
                return None
            value, ts = self._store[key]
            if _time.time() - ts < (ttl or self.default_ttl):
                self._store.move_to_end(key)
                return value
            del self._store[key]
            return None

    def set(self, key: str, value: object):
        """写入缓存，超容时自动淘汰最旧条目。"""
        with self._lock:
            self._store[key] = (value, _time.time())
            self._store.move_to_end(key)
            if len(self._store) > self.max_size:
                for _ in range(self.evict_batch):
                    self._store.popitem(last=False)

    def invalidate(self, substring: str):
        """清除键包含 substring 的所有缓存条目（通常用 user_id 作为匹配串）。"""
        with self._lock:
            to_delete = [k for k in self._store if substring in k]
            for k in to_delete:
                del self._store[k]

    def clear(self):
        """清空所有缓存。"""
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        return len(self._store)

    @property
    def size(self) -> int:
        return len(self._store)

    @property
    def keys(self):
        return list(self._store.keys())


# 模块级单例，供 server.py 和各 router 共享
default_cache = TTLCache(max_size=500, evict_batch=100, default_ttl=180)
