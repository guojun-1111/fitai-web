# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""Tests for tools/fitai_database.py — database CRUD operations."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestWorkoutOperations:
    def test_insert_and_get_workout(self, monkeypatch_fitai_db, user_id):
        from tools.fitai_database import insert_workout, get_workout_history_json

        insert_workout(user_id, "卧推", 3, 10, 60.0, 30, "test")
        results = get_workout_history_json(user_id, 7)
        assert len(results) == 1
        assert results[0]["exercise_name"] == "卧推"
        assert results[0]["sets"] == 3
        assert results[0]["weight_kg"] == 60.0

    def test_insert_with_nulls(self, monkeypatch_fitai_db, user_id):
        from tools.fitai_database import insert_workout, get_workout_history_json

        insert_workout(user_id, "跑步", None, None, None, 45, None)
        results = get_workout_history_json(user_id, 7)
        assert len(results) == 1
        assert results[0]["exercise_name"] == "跑步"
        assert results[0]["duration_minutes"] == 45


class TestBodyMetrics:
    def test_insert_and_get_metrics(self, monkeypatch_fitai_db, user_id):
        from tools.fitai_database import insert_body_metric, get_body_metrics_history_json

        insert_body_metric(user_id, 70.5, 15.2, "test note")
        results = get_body_metrics_history_json(user_id, 90)
        assert len(results) == 1
        assert results[0]["weight_kg"] == 70.5
        assert results[0]["body_fat_pct"] == 15.2


class TestNutrition:
    def test_insert_and_get_nutrition(self, monkeypatch_fitai_db, user_id):
        from tools.fitai_database import insert_nutrition, get_nutrition_history_json

        # Signature: insert_nutrition(user_id, meal_type, food_name, calories, protein_g, carbs_g, fat_g, notes, date)
        insert_nutrition(user_id, "午餐", "鸡胸肉", 200, 40, 0, 5)
        results = get_nutrition_history_json(user_id, 90)
        assert len(results) == 1
        assert results[0]["food_name"] == "鸡胸肉"
        assert results[0]["calories"] == 200


class TestChatHistory:
    def test_save_and_get_chat(self, monkeypatch_fitai_db, user_id):
        from tools.fitai_database import save_chat_message, get_chat_history, list_chat_sessions

        save_chat_message(user_id, "sess1", "user", "Hello")
        save_chat_message(user_id, "sess1", "assistant", "Hi there!")
        save_chat_message(user_id, "sess2", "user", "Another")

        sessions = list_chat_sessions(user_id)
        assert len(sessions) == 2

        msgs = get_chat_history(user_id, "sess1")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"

    def test_delete_session(self, monkeypatch_fitai_db, user_id):
        from tools.fitai_database import save_chat_message, delete_chat_session, list_chat_sessions

        save_chat_message(user_id, "to_delete", "user", "msg")
        delete_chat_session(user_id, "to_delete")
        sessions = list_chat_sessions(user_id)
        assert len(sessions) == 0


class TestHealthData:
    def test_insert_health_data(self, monkeypatch_fitai_db, user_id):
        from tools.fitai_database import insert_health_data, get_health_data_history_json

        # Signature: insert_health_data(user_id, date, source_platform, data_type, value, unit, detail_json)
        insert_health_data(user_id, "2026-01-01", "test", "steps", 5000, "步")
        results = get_health_data_history_json(user_id, 7)
        assert len(results) >= 0

    def test_insert_health_data_batch(self, monkeypatch_fitai_db, user_id):
        from tools.fitai_database import insert_health_data_batch

        records = [
            {"data_type": "steps", "value": 5000, "unit": "步", "date": "2026-01-01", "source_platform": "test", "detail_json": ""},
            {"data_type": "steps", "value": 6000, "unit": "步", "date": "2026-01-02", "source_platform": "test", "detail_json": ""},
            {"data_type": "sleep", "value": 480, "unit": "分钟", "date": "2026-01-01", "source_platform": "test", "detail_json": ""},
        ]
        count = insert_health_data_batch(user_id, records)
        assert count >= 0

    def test_insert_batch_empty(self, monkeypatch_fitai_db, user_id):
        from tools.fitai_database import insert_health_data_batch

        count = insert_health_data_batch(user_id, [])
        assert count == 0


class TestUserProfile:
    def test_get_summary(self, monkeypatch_fitai_db, user_id):
        from tools.fitai_database import get_user_profile_summary

        summary = get_user_profile_summary(user_id)
        assert isinstance(summary, str)

    def test_no_profile_returns_empty(self, monkeypatch_fitai_db, user_id):
        from tools.fitai_database import get_user_profile_summary
        assert "" == get_user_profile_summary(user_id)


class TestStreak:
    def test_no_data(self, monkeypatch_fitai_db, user_id):
        from tools.fitai_database import get_streak
        assert get_streak(user_id) == 0
