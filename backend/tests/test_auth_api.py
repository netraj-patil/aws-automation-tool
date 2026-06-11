"""API contract tests for local account authentication."""

from fastapi.testclient import TestClient

from app.main import app
from app.routes import auth_routes
from app.services.auth_service import AuthService


def _client(monkeypatch, tmp_path) -> TestClient:
    service = AuthService(tmp_path / "auth.db", jwt_secret="test-secret")
    monkeypatch.setattr(auth_routes, "auth_service", service)
    return TestClient(app)


def test_register_returns_token_and_user(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Demo User",
            "email": "Demo@Example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["access_token"].count(".") == 2
    assert payload["token_type"] == "bearer"
    assert payload["user"]["name"] == "Demo User"
    assert payload["user"]["email"] == "demo@example.com"


def test_login_accepts_registered_credentials(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    client.post(
        "/api/v1/auth/register",
        json={
            "name": "Demo User",
            "email": "demo@example.com",
            "password": "password123",
        },
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "demo@example.com", "password": "password123"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "demo@example.com"


def test_duplicate_registration_returns_conflict(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    payload = {
        "name": "Demo User",
        "email": "demo@example.com",
        "password": "password123",
    }
    client.post("/api/v1/auth/register", json=payload)

    response = client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "An account with this email already exists."
    )


def test_login_rejects_wrong_password(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    client.post(
        "/api/v1/auth/register",
        json={
            "name": "Demo User",
            "email": "demo@example.com",
            "password": "password123",
        },
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "demo@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password."
