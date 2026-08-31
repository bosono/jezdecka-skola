import pytest
from app import create_app


@pytest.fixture
def client(temp_env):
    application = create_app()
    application.config.update(TESTING=True)
    return application.test_client()


@pytest.fixture
def auth_client(client):
    client.post("/api/login", json={"password": "test-pw"})
    return client


EMPTY = {"horses": [], "riders": [], "slots": [], "assignments": []}


def test_state_requires_login(client):
    assert client.get("/api/state").status_code == 401


def test_get_state_default(auth_client):
    resp = auth_client.get("/api/state")
    assert resp.status_code == 200
    assert resp.get_json() == {"version": 0, "data": None}


def test_put_then_get_round_trip(auth_client):
    resp = auth_client.put("/api/state", json={"version": 0, "data": EMPTY})
    assert resp.status_code == 200
    assert resp.get_json()["version"] == 1
    got = auth_client.get("/api/state").get_json()
    assert got == {"version": 1, "data": EMPTY}


def test_put_stale_version_conflict(auth_client):
    auth_client.put("/api/state", json={"version": 0, "data": EMPTY})
    resp = auth_client.put("/api/state", json={"version": 0, "data": EMPTY})
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["conflict"] is True
    assert body["version"] == 1


def test_put_bad_body_is_400(auth_client):
    assert auth_client.put("/api/state", json={"data": EMPTY}).status_code == 400
    assert auth_client.put("/api/state", json={"version": 0}).status_code == 400


def test_root_serves_html(auth_client):
    resp = auth_client.get("/")
    assert resp.status_code == 200
    assert b"Jezdeck" in resp.data
