import pytest
from app import create_app


@pytest.fixture
def client(temp_env):
    application = create_app()
    application.config.update(TESTING=True)
    return application.test_client()


def test_ping_is_public(client):
    resp = client.get("/api/ping")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}


def test_login_wrong_password(client):
    resp = client.post("/api/login", json={"password": "spatne"})
    assert resp.status_code == 401
    assert resp.get_json()["ok"] is False


def test_login_correct_password_sets_session(client):
    resp = client.post("/api/login", json={"password": "test-pw"})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_logout_clears_session(client):
    client.post("/api/login", json={"password": "test-pw"})
    resp = client.post("/api/logout")
    assert resp.status_code == 200
