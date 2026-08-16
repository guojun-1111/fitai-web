# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

import base64
import os

from core import crypto as c


def _reset():
    c._key_cache = None
    c._key_warned = False


def _set_key(monkeypatch):
    key = base64.b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("ENCRYPTION_SECRET_KEY", key)
    _reset()
    return key


def test_roundtrip(monkeypatch):
    _set_key(monkeypatch)
    token = c.encrypt_field("hello world")
    assert token.startswith("enc:v1:")
    assert token != "hello world"
    assert c.decrypt_field(token) == "hello world"


def test_plaintext_fallback(monkeypatch):
    monkeypatch.delenv("ENCRYPTION_SECRET_KEY", raising=False)
    _reset()
    assert c.encrypt_field("plain") == "plain"
    assert c.decrypt_field("plain") == "plain"


def test_empty():
    assert c.encrypt_field("") == ""
    assert c.encrypt_field(None) == ""
    assert c.decrypt_field("") == ""
    assert c.decrypt_field(None) == ""


def test_tamper_detection(monkeypatch):
    _set_key(monkeypatch)
    token = c.encrypt_field("secret")
    raw = bytearray(base64.b64decode(token[len(c._PREFIX):]))
    raw[12] ^= 0xFF  # corrupt first ciphertext byte
    bad = c._PREFIX + base64.b64encode(bytes(raw)).decode()
    assert c.decrypt_field(bad) == ""


def test_unique_nonces(monkeypatch):
    _set_key(monkeypatch)
    a = c.encrypt_field("same")
    b = c.encrypt_field("same")
    assert a != b  # random nonce => different ciphertext


def test_is_encrypted():
    assert c.is_encrypted("enc:v1:abc")
    assert not c.is_encrypted("plain")
    assert not c.is_encrypted(None)
