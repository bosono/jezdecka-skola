import json
import os
import sqlite3
from datetime import datetime, timezone


def _db_path():
    return os.environ.get("DB_PATH", "skola.db")


def _backup_dir():
    return os.environ.get("BACKUP_DIR", "")


def _conn():
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data TEXT,
                version INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO state (id, data, version, updated_at) VALUES (1, NULL, 0, NULL)"
        )
        row = conn.execute("SELECT data FROM state WHERE id = 1").fetchone()
        if row is not None and not row["data"]:
            seed = _load_seed()
            if seed is not None:
                now = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    "UPDATE state SET data = ?, version = 1, updated_at = ? WHERE id = 1",
                    (json.dumps(seed, ensure_ascii=False), now),
                )


def _load_seed():
    path = os.environ.get(
        "SEED_PATH", os.path.join(os.path.dirname(__file__), "seed.json")
    )
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def get_state():
    with _conn() as conn:
        row = conn.execute("SELECT data, version FROM state WHERE id = 1").fetchone()
    if row is None:
        return {"version": 0, "data": None}
    data = json.loads(row["data"]) if row["data"] else None
    return {"version": row["version"], "data": data}


def put_state(data, expected_version):
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        row = conn.execute("SELECT version FROM state WHERE id = 1").fetchone()
        current = row["version"] if row else 0
        if expected_version != current:
            return None
        new_version = current + 1
        conn.execute(
            "UPDATE state SET data = ?, version = ?, updated_at = ? WHERE id = 1",
            (json.dumps(data, ensure_ascii=False), new_version, now),
        )
    _write_backup(data, now)
    return new_version


def _write_backup(data, now):
    backup_dir = _backup_dir()
    if not backup_dir:
        return
    os.makedirs(backup_dir, exist_ok=True)
    stamp = "".join(c for c in now if c.isdigit())[:14]
    path = os.path.join(backup_dir, f"skola-{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    _prune_backups(backup_dir, keep=30)


def _prune_backups(backup_dir, keep):
    files = sorted(
        f for f in os.listdir(backup_dir) if f.startswith("skola-") and f.endswith(".json")
    )
    for f in files[:-keep]:
        try:
            os.remove(os.path.join(backup_dir, f))
        except OSError:
            pass
