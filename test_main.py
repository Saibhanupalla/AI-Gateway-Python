"""
Tests for AI Gateway API endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def get_token(username: str, password: str) -> dict:
    response = client.post("/token", data={"username": username, "password": password})
    return response.json()


def auth_header(username: str = "admin", password: str = "admin123") -> dict:
    token = get_token(username, password)
    return {"Authorization": f"Bearer {token['access_token']}"}


# ─── Auth ────────────────────────────────────────────────────────────────────

def test_login_success():
    response = client.post("/token", data={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_failure():
    response = client.post("/token", data={"username": "admin", "password": "wrongpassword"})
    assert response.status_code == 401


def test_read_users_me():
    response = client.get("/users/me/", headers=auth_header("user", "user123"))
    assert response.status_code == 200
    assert response.json()["username"] == "user"


# ─── Health ──────────────────────────────────────────────────────────────────

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_readiness():
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "AI Gateway" in response.json()["message"]


# ─── Prompt (without real LLM key — expects error response) ─────────────────

def test_create_prompt_without_auth():
    response = client.post("/prompt", json={"prompt": "test prompt"})
    assert response.status_code == 401


def test_create_prompt_with_auth():
    """With auth but likely no valid API key, we get a response with gateway error."""
    response = client.post(
        "/prompt",
        headers=auth_header("user", "user123"),
        json={"prompt": "Hello, what is 2+2?"}
    )
    assert response.status_code == 200
    data = response.json()
    # Should have the enterprise response structure
    assert "masked_prompt" in data
    assert "llm_response" in data
    assert "model" in data
    assert "provider" in data
    assert "tokens_used" in data
    assert "cost_usd" in data
    assert "cache_hit" in data
    assert "latency_ms" in data


# ─── Admin Prompt ────────────────────────────────────────────────────────────

def test_admin_prompt_with_user():
    """Regular users should not access admin prompt."""
    response = client.post(
        "/admin/prompt",
        headers=auth_header("user", "user123"),
        json={"prompt": "admin test"}
    )
    assert response.status_code == 403


# ─── Users CRUD ──────────────────────────────────────────────────────────────

def test_create_user_as_admin():
    response = client.post(
        "/users",
        headers=auth_header(),
        json={
            "username": "testuser_pytest",
            "password": "testpass",
            "full_name": "Test User",
            "email": "test@example.com",
            "role": "user",
        }
    )
    # May already exist from previous test runs
    assert response.status_code in (200, 400)


def test_create_user_as_regular_user():
    """Regular users should not create other users."""
    response = client.post(
        "/users",
        headers=auth_header("user", "user123"),
        json={"username": "hacker", "password": "hack"}
    )
    assert response.status_code == 403


# ─── Policy CRUD ─────────────────────────────────────────────────────────────

def test_policy_crud():
    headers = auth_header()

    # Create
    response = client.post("/admin/policies", headers=headers, json={
        "effect": "deny", "resource": "prompt", "action": "create",
        "target_role": "test_role"
    })
    assert response.status_code == 200
    policy_id = response.json()["id"]

    # List
    response = client.get("/admin/policies", headers=headers)
    assert response.status_code == 200
    assert any(p["id"] == policy_id for p in response.json())

    # Delete
    response = client.delete(f"/admin/policies/{policy_id}", headers=headers)
    assert response.status_code == 200


# ─── Rate Limit CRUD ─────────────────────────────────────────────────────────

def test_rate_limit_crud():
    headers = auth_header()

    response = client.post("/admin/rate-limits", headers=headers, json={
        "scope": "user", "target": "testuser", "window": "hour",
        "max_tokens": 100000, "max_requests": 100
    })
    assert response.status_code == 200
    limit_id = response.json()["id"]

    response = client.get("/admin/rate-limits", headers=headers)
    assert response.status_code == 200

    response = client.delete(f"/admin/rate-limits/{limit_id}", headers=headers)
    assert response.status_code == 200


# ─── Guardrails CRUD ─────────────────────────────────────────────────────────

def test_guardrail_crud():
    headers = auth_header()

    response = client.post("/admin/guardrails", headers=headers, json={
        "name": "Test max length",
        "stage": "pre",
        "check_type": "max_length",
        "config_json": '{"max_characters": 5000}',
        "action": "block"
    })
    assert response.status_code == 200
    gr_id = response.json()["id"]

    response = client.get("/admin/guardrails", headers=headers)
    assert response.status_code == 200

    response = client.delete(f"/admin/guardrails/{gr_id}", headers=headers)
    assert response.status_code == 200


# ─── Templates CRUD ──────────────────────────────────────────────────────────

def test_template_crud():
    headers = auth_header()

    # Create
    response = client.post("/templates", headers=headers, json={
        "name": "Test Summarizer",
        "template_text": "Summarize the following: {{text}}",
        "model_hint": "gpt-4o-mini",
        "description": "A test summarization template"
    })
    assert response.status_code == 200
    template_id = response.json()["id"]

    # List
    response = client.get("/templates", headers=auth_header("user", "user123"))
    assert response.status_code == 200

    # Render
    response = client.post(
        f"/templates/{template_id}/render",
        headers=auth_header("user", "user123"),
        json={"text": "Hello world!"}
    )
    assert response.status_code == 200
    assert "Hello world!" in response.json()["rendered"]

    # Delete (soft)
    response = client.delete(f"/templates/{template_id}", headers=headers)
    assert response.status_code == 200


# ─── Analytics ───────────────────────────────────────────────────────────────

def test_analytics_summary():
    response = client.get("/analytics/summary", headers=auth_header())
    assert response.status_code == 200
    data = response.json()
    assert "total_requests" in data
    assert "total_cost_usd" in data
    assert "model_usage" in data


def test_analytics_requests():
    response = client.get("/analytics/requests?limit=10", headers=auth_header())
    assert response.status_code == 200


def test_analytics_users():
    response = client.get("/analytics/users", headers=auth_header())
    assert response.status_code == 200


# ─── Audit Logs ──────────────────────────────────────────────────────────────

def test_audit_logs():
    response = client.get("/audit_logs", headers=auth_header())
    assert response.status_code == 200


def test_audit_logs_requires_admin():
    response = client.get("/audit_logs", headers=auth_header("user", "user123"))
    assert response.status_code == 403


# ─── Gateway Config ──────────────────────────────────────────────────────────

def test_gateway_config():
    response = client.get("/gateway/config", headers=auth_header())
    assert response.status_code == 200
    data = response.json()
    assert "providers" in data
    assert "routing" in data