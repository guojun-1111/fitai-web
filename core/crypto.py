# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Field-level encryption (AES-256-GCM).

Stored format: ``enc:v1:<base64(nonce || ciphertext || tag)>``.

The master key comes from the ``ENCRYPTION_SECRET_KEY`` env var (32-byte
base64). ``decrypt_field`` returns plaintext values unchanged, so legacy
un-encrypted rows keep working and migration can be done incrementally.
"""
import os
import base64
import logging

from Crypto.Cipher import AES

logger = logging.getLogger(__name__)

_PREFIX = "enc:v1:"
_NONCE_LEN = 12
_TAG_LEN = 16
_KEY_LEN = 32

_key_cache = None
_key_warned = False


def _get_key():
    global _key_cache, _key_warned
    if _key_cache is not None:
        return _key_cache
    key_b64 = os.getenv("ENCRYPTION_SECRET_KEY", "")
    if not key_b64:
        if not _key_warned:
            logger.warning(
                "ENCRYPTION_SECRET_KEY is not set — field encryption disabled; "
                "sensitive data will be stored in plaintext. Set a 32-byte base64 key."
            )
            _key_warned = True
        _key_cache = None
        return None
    try:
        key = base64.b64decode(key_b64)
    except Exception:
        logger.error("ENCRYPTION_SECRET_KEY is not valid base64")
        _key_cache = None
        return None
    if len(key) != _KEY_LEN:
        logger.error(
            "ENCRYPTION_SECRET_KEY must decode to %d bytes (got %d)", _KEY_LEN, len(key)
        )
        _key_cache = None
        return None
    _key_cache = key
    return key


def encrypt_field(plaintext) -> str:
    """Encrypt a string. Returns '' for empty, plaintext unchanged if no key."""
    if plaintext is None:
        return ""
    plaintext = str(plaintext)
    if plaintext == "":
        return ""
    key = _get_key()
    if key is None:
        return plaintext  # no key configured: leave as-is (warning already logged)
    nonce = os.urandom(_NONCE_LEN)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode("utf-8"))
    return _PREFIX + base64.b64encode(nonce + ciphertext + tag).decode("ascii")


def decrypt_field(token) -> str:
    """Decrypt an ``enc:v1:`` value. Plaintext (no prefix) is returned unchanged."""
    if token is None:
        return ""
    token = str(token)
    if token == "":
        return ""
    if not token.startswith(_PREFIX):
        return token  # legacy plaintext
    key = _get_key()
    if key is None:
        return token  # cannot decrypt without key
    try:
        raw = base64.b64decode(token[len(_PREFIX):])
        nonce = raw[:_NONCE_LEN]
        ciphertext = raw[_NONCE_LEN:-_TAG_LEN]
        tag = raw[-_TAG_LEN:]
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")
    except Exception:
        logger.error("Failed to decrypt field (wrong key or tampered data)")
        return ""


def is_encrypted(token) -> bool:
    return isinstance(token, str) and token.startswith(_PREFIX)
