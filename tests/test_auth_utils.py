# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""Tests for auth/utils.py — security-critical functions."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth.utils import (
    validate_password,
    validate_username,
    hash_password,
    verify_password,
)


class TestPasswordValidation:
    def test_valid_password(self):
        ok, msg = validate_password("MyPass123")
        assert ok is True
        assert msg == ""

    def test_too_short(self):
        ok, msg = validate_password("Ab1")
        assert ok is False

    def test_no_uppercase(self):
        ok, msg = validate_password("mypassword1")
        assert ok is False

    def test_no_lowercase(self):
        ok, msg = validate_password("MYPASSWORD1")
        assert ok is False

    def test_no_digit(self):
        ok, msg = validate_password("MyPassword")
        assert ok is False

    def test_minimum_length(self):
        ok, msg = validate_password("Ab123456")
        assert ok is True


class TestUsernameValidation:
    def test_valid_username(self):
        ok, msg = validate_username("testuser")
        assert ok is True

    def test_valid_with_numbers(self):
        ok, msg = validate_username("user123")
        assert ok is True

    def test_valid_with_underscore(self):
        ok, msg = validate_username("user_name")
        assert ok is True

    def test_too_short(self):
        ok, msg = validate_username("ab")
        assert ok is False

    def test_too_long(self):
        ok, msg = validate_username("a" * 33)
        assert ok is False

    def test_special_chars(self):
        ok, msg = validate_username("user!@#")
        assert ok is False


class TestPasswordHashing:
    def test_hash_and_verify(self):
        hashed = hash_password("MyPassword123")
        assert verify_password("MyPassword123", hashed) is True

    def test_wrong_password(self):
        hashed = hash_password("MyPassword123")
        assert verify_password("WrongPassword", hashed) is False

    def test_different_passwords_different_hashes(self):
        h1 = hash_password("Password1")
        h2 = hash_password("Password2")
        assert h1 != h2

    def test_invalid_hash_format(self):
        assert verify_password("anything", "not-a-valid-hash") is False

    def test_empty_hash(self):
        assert verify_password("anything", "") is False
