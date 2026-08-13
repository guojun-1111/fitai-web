# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""V7.0: 全局运行时状态（从 server.py 提取，供各 router 读写）。"""
_current_model = "deepseek-v4-flash"
_reply_style = "casual"  # casual | data


def get_model() -> str:
    return _current_model


def set_model(model: str) -> bool:
    global _current_model
    if model in ("deepseek-v4-pro", "deepseek-v4-flash"):
        _current_model = model
        return True
    return False


def get_reply_style() -> str:
    return _reply_style


def set_reply_style(style: str) -> bool:
    global _reply_style
    if style in ("casual", "data"):
        _reply_style = style
        return True
    return False
