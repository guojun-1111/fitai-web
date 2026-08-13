# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""V7.0 提取: 异步 SQLite 查询工具。

从 server.py 提取，将同步 SQLite 查询放入线程池以不阻塞事件循环。
"""
import asyncio as _asyncio


async def db_fetch(query: str, params=()):
    """在线程池中执行同步 SQLite 查询，不阻塞 asyncio 事件循环。

    Args:
        query: SQL 查询语句
        params: 查询参数元组

    Returns:
        fetchall() 的结果列表
    """
    from tools.fitai_database import get_db

    def _run():
        conn = get_db()
        return conn.execute(query, params).fetchall()

    return await _asyncio.get_event_loop().run_in_executor(None, _run)


async def db_execute(query: str, params=()):
    """在线程池中执行同步 SQLite 写操作（INSERT/UPDATE/DELETE）。

    Args:
        query: SQL 语句
        params: 参数元组

    Returns:
        cursor.lastrowid
    """
    from tools.fitai_database import get_db

    def _run():
        conn = get_db()
        cur = conn.execute(query, params)
        conn.commit()
        return cur.lastrowid

    return await _asyncio.get_event_loop().run_in_executor(None, _run)


async def db_executemany(query: str, params_list: list):
    """在线程池中执行批量 SQLite 写操作。

    Args:
        query: SQL 语句
        params_list: 参数列表

    Returns:
        cursor.rowcount
    """
    from tools.fitai_database import get_db

    def _run():
        conn = get_db()
        cur = conn.executemany(query, params_list)
        conn.commit()
        return cur.rowcount

    return await _asyncio.get_event_loop().run_in_executor(None, _run)
