# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""集成测试：登录 → 业务 API 关键链路（验证重构后路由注册与认证正常）。"""


def test_health_check(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("ok", "degraded")


def test_auth_required(client):
    client.headers.pop("Authorization", None)
    resp = client.get("/api/profile")
    assert resp.status_code == 401


def test_profile_roundtrip(client):
    """写读用户画像（加密字段往返，无密钥时明文 fallback 不崩）。"""
    resp = client.post("/api/profile", json={"name": "张三", "gender": "男"})
    assert resp.status_code == 200
    resp = client.get("/api/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "张三"
    assert data["gender"] == "男"


def test_health_record_roundtrip(client, test_db):
    """写读健康数据（写→读一致性，呼应安全验证要求）。"""
    resp = client.post("/api/health/record", json={"data_type": "steps", "value": 8000})
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    row = test_db.execute("SELECT value FROM health_data WHERE data_type='steps'").fetchone()
    assert row is not None and float(row["value"]) == 8000


def test_chat_sessions(client):
    resp = client.get("/api/chat/sessions")
    assert resp.status_code == 200
    assert "sessions" in resp.json()


def test_privacy_export(client):
    resp = client.get("/api/privacy/export")
    assert resp.status_code == 200
    assert "application/zip" in resp.headers["content-type"]


def test_account_delete(client):
    resp = client.delete("/api/privacy/account")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_llm_test_no_crash(client):
    """修复 get_user_id NameError 后，/api/llm-test 不应再 500。"""
    resp = client.get("/api/llm-test")
    assert resp.status_code == 200
    assert "provider" in resp.json()
