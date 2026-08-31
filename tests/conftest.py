import pytest


@pytest.fixture
def temp_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("APP_PASSWORD", "test-pw")
    return tmp_path
