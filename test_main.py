import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def get_token(username: str, password: str):
    response = client.post(
        "/token",
        data={"username": username, "password": password}
    )
    return response.json()

def test_login_success():
    response = client.post(
        "/token",
        data={"username": "admin", "password": "admin123"}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()

def test_login_failure():
    response = client.post(
        "/token",
        data={"username": "admin", "password": "wrongpassword"}
    )
    assert response.status_code == 401

def test_read_users_me():
    token = get_token("user", "user123")
    response = client.get(
        "/users/me/",
        headers={"Authorization": f"Bearer {token['access_token']}"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == "user"

def test_create_prompt_with_auth():
    token = get_token("user", "user123")
    response = client.post(
        "/prompt",
        headers={"Authorization": f"Bearer {token['access_token']}"},
        json={"prompt": "test prompt"}
    )
    assert response.status_code == 200
    assert "test prompt" in response.json()["response"]

def test_create_prompt_without_auth():
    response = client.post(
        "/prompt",
        json={"prompt": "test prompt"}
    )
    assert response.status_code == 401

def test_admin_prompt_with_admin():
    token = get_token("admin", "admin123")
    response = client.post(
        "/admin/prompt",
        headers={"Authorization": f"Bearer {token['access_token']}"},
        json={"prompt": "admin test"}
    )
    assert response.status_code == 200
    assert "admin test" in response.json()["response"]

def test_admin_prompt_with_user():
    token = get_token("user", "user123")
    response = client.post(
        "/admin/prompt",
        headers={"Authorization": f"Bearer {token['access_token']}"},
        json={"prompt": "admin test"}
    )
    assert response.status_code == 403


def test_create_user_as_admin_and_duplicate():
    admin_token = get_token("admin", "admin123")
    # create a new user
    response = client.post(
        "/users",
        headers={"Authorization": f"Bearer {admin_token['access_token']}"},
        json={"username": "newuser", "password": "newpass", "full_name": "New User", "email": "new@example.com", "role": "user"}
    )
    # depending on DB state this may already exist from previous runs
    assert response.status_code in (200, 400)
    if response.status_code == 200:
        assert response.json()["username"] == "newuser"
    else:
        assert response.json().get("detail") in ("username already exists",)

    # attempt to create the same user again
    response2 = client.post(
        "/users",
        headers={"Authorization": f"Bearer {admin_token['access_token']}"},
        json={"username": "newuser", "password": "newpass", "full_name": "New User", "email": "new@example.com", "role": "user"}
    )
    assert response2.status_code == 400