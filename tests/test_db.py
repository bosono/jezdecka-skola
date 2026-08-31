import json
import os
import db


def test_get_state_empty_returns_null_data(temp_env):
    db.init_db()
    state = db.get_state()
    assert state == {"version": 0, "data": None}


def test_put_state_persists_and_bumps_version(temp_env):
    db.init_db()
    payload = {"horses": [{"id": "h1", "name": "Dally"}], "riders": [], "slots": [], "assignments": []}
    new_version = db.put_state(payload, expected_version=0)
    assert new_version == 1
    state = db.get_state()
    assert state["version"] == 1
    assert state["data"] == payload


def test_put_state_stale_version_returns_none(temp_env):
    db.init_db()
    db.put_state({"horses": [], "riders": [], "slots": [], "assignments": []}, expected_version=0)
    result = db.put_state({"horses": [], "riders": [], "slots": [], "assignments": []}, expected_version=0)
    assert result is None


def test_put_state_writes_backup_file(temp_env):
    db.init_db()
    db.put_state({"horses": [], "riders": [], "slots": [], "assignments": []}, expected_version=0)
    backups = os.listdir(temp_env / "backups")
    assert len(backups) == 1
    with open(temp_env / "backups" / backups[0], encoding="utf-8") as f:
        assert json.load(f) == {"horses": [], "riders": [], "slots": [], "assignments": []}


def test_unicode_survives_round_trip(temp_env):
    db.init_db()
    payload = {"horses": [{"id": "h1", "name": "Šiml"}], "riders": [], "slots": [], "assignments": []}
    db.put_state(payload, expected_version=0)
    assert db.get_state()["data"]["horses"][0]["name"] == "Šiml"
