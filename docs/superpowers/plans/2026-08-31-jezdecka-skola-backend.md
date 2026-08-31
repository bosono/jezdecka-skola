# Jezdecká škola — Backend (Fáze 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Přidat k existujícímu single-file prototypu (`index.html`) tenký Flask backend, který ukládá data serverově místo do localStorage, chrání je jedním sdíleným heslem a je nasaditelný na Railway.

**Architecture:** Aplikace má jeden sdílený dataset (celý objekt `S = {horses, riders, slots, assignments}`). Backend ho drží jako jeden JSON blob v SQLite (tabulka `state`, jeden řádek) s celočíselnou `version` pro optimistický zámek. Dvě chráněné operace: `GET /api/state` (načíst) a `PUT /api/state` (uložit s kontrolou verze). Frontend zůstává jeden soubor — mění se pouze `load()`/`save()` na `fetch` a přibývá přihlašovací overlay. Datová vrstva je izolovaná v `db.py`, takže pozdější přechod na Postgres je malá změna.

**Tech Stack:** Python 3.11+, Flask 3.x, gunicorn (produkce), SQLite (stdlib `sqlite3`, bez ORM), pytest. Frontend beze změny stacku (vanilla JS v `index.html`).

## Global Constraints

- **Jazyk UI i hlášek:** čeština (frontend i chybové texty viditelné uživateli).
- **Autentizace:** jedno sdílené heslo z env `APP_PASSWORD`, session cookie podepsaná `SECRET_KEY` (env). Žádné uživatelské účty.
- **Databáze:** SQLite, cesta z env `DB_PATH` (default `skola.db`). Bez ORM, jen stdlib `sqlite3`.
- **Závislosti minimální:** pouze `flask`, `gunicorn`. Nic dalšího do `requirements.txt` bez důvodu.
- **Frontend zůstává jeden soubor** `index.html` — nerozbíjet do modulů, neintrodukovat build krok ani JS test runner.
- **Deploy:** Railway, SQLite na perzistentním volume mountnutém na `/data` (`DB_PATH=/data/skola.db`).
- **Konkurence:** optimistický zámek přes `version`; poslední zapisující s neaktuální verzí dostane 409 a přenačte.
- **DB env se čte za běhu (uvnitř funkcí), ne při importu** — kvůli testovatelnosti s dočasnou DB.

---

## File Structure

```
jezdecka-skola/
  index.html          # MODIFY: load()/save() → API, login overlay, verze
  db.py               # CREATE: SQLite state store (init_db, get_state, put_state, backup)
  app.py              # CREATE: Flask app factory, auth, state API, servírování index.html
  requirements.txt    # CREATE: flask, gunicorn
  Procfile            # CREATE: web: gunicorn app:app
  runtime.txt         # CREATE: python-3.11.x (Railway pin)
  .env.example        # CREATE: vzor env proměnných
  .gitignore          # MODIFY: přidat skola.db, .env, backups/, __pycache__, venv
  tests/
    conftest.py       # CREATE: test client fixture s dočasnou DB
    test_db.py        # CREATE: unit testy db.py
    test_auth.py      # CREATE: testy login/logout/ochrany
    test_state.py     # CREATE: testy GET/PUT/konflikt/round-trip
  README.md           # MODIFY: sekce Fáze 2 – lokální běh + deploy Railway
  docs/superpowers/...
```

**Zodpovědnosti:**
- `db.py` — veškerá práce s SQLite a se soubory záloh. Nezná Flask.
- `app.py` — HTTP vrstva: routy, session, autentizace, validace vstupu, servírování `index.html`. Data deleguje na `db.py`.
- `index.html` — UI a in-memory model beze změny; persistence přes `fetch`.

---

### Task 1: Scaffolding + datová vrstva `db.py`

**Files:**
- Create: `requirements.txt`
- Create: `db.py`
- Create: `tests/conftest.py`
- Create: `tests/test_db.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces:
  - `db.init_db() -> None` — vytvoří tabulku `state` a zajistí existenci řádku `id=1`.
  - `db.get_state() -> dict` — vrací `{"version": int, "data": dict | None}`. `data` je `None`, dokud nikdo neuložil.
  - `db.put_state(data: dict, expected_version: int) -> int | None` — při shodě verze uloží, vrátí novou verzi; při neshodě vrátí `None` (konflikt).
  - Env čtené za běhu: `DB_PATH` (default `"skola.db"`), `BACKUP_DIR` (default `""` = zálohy vypnuté).

- [ ] **Step 1: requirements.txt**

Create `requirements.txt`:

```
flask>=3.0,<4.0
gunicorn>=21.0
```

- [ ] **Step 2: .gitignore doplnit**

Připoj na konec `.gitignore`:

```
.env
skola.db
skola.db-journal
backups/
__pycache__/
*.pyc
venv/
.venv/
```

- [ ] **Step 3: conftest s dočasnou DB**

Create `tests/conftest.py`:

```python
import pytest


@pytest.fixture
def temp_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("APP_PASSWORD", "test-pw")
    return tmp_path
```

- [ ] **Step 4: Napsat padající testy db.py**

Create `tests/test_db.py`:

```python
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
```

- [ ] **Step 5: Ověřit, že testy padají**

Run: `cd ~/Documents/Claude/jezdecka-skola && python3 -m pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'db'`.

- [ ] **Step 6: Implementovat db.py**

Create `db.py`:

```python
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
```

- [ ] **Step 7: Ověřit, že testy prošly**

Run: `python3 -m pytest tests/test_db.py -v`
Expected: PASS (5 testů).

> Poznámka: `test_put_state_writes_backup_file` může teoreticky vygenerovat stejný časový otisk pro dvě zálohy ve stejné sekundě, ale v tomto testu se ukládá jen jednou. Pořadí kroků zajišťuje jeden soubor.

- [ ] **Step 8: Commit**

```bash
cd ~/Documents/Claude/jezdecka-skola
git add requirements.txt db.py tests/conftest.py tests/test_db.py .gitignore
git commit -m "Backend: SQLite state store (db.py) s optimistickým zámkem a zálohami"
```

---

### Task 2: Flask app factory + autentizace

**Files:**
- Create: `app.py`
- Create: `tests/test_auth.py`

**Interfaces:**
- Consumes: `db.init_db` (Task 1).
- Produces:
  - `app.create_app() -> flask.Flask` — factory; čte `SECRET_KEY` a `APP_PASSWORD` z env, volá `db.init_db()`, registruje routy.
  - `app.app` — modul-level instance pro gunicorn (`gunicorn app:app`).
  - Routy: `POST /api/login` (body `{"password": str}` → 200 `{"ok": true}` / 401), `POST /api/logout` (→ 200), `GET /api/ping` (→ 200 `{"ok": true}`, bez auth).
  - Dekorátor `login_required` chránící následné routy (401 bez session).

- [ ] **Step 1: Napsat padající testy autentizace**

Create `tests/test_auth.py`:

```python
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
```

- [ ] **Step 2: Ověřit, že testy padají**

Run: `python3 -m pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app'`.

- [ ] **Step 3: Implementovat app.py (factory + auth)**

Create `app.py`:

```python
import hmac
import os
from datetime import timedelta
from functools import wraps

from flask import Flask, abort, jsonify, request, send_file, session

import db


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("auth"):
            abort(401)
        return f(*args, **kwargs)

    return wrapper


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ["SECRET_KEY"]
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )
    app_password = os.environ["APP_PASSWORD"]

    db.init_db()

    @app.get("/api/ping")
    def ping():
        return jsonify({"ok": True})

    @app.post("/api/login")
    def login():
        body = request.get_json(silent=True) or {}
        if hmac.compare_digest(str(body.get("password", "")), app_password):
            session["auth"] = True
            session.permanent = True
            return jsonify({"ok": True})
        return jsonify({"ok": False}), 401

    @app.post("/api/logout")
    def logout():
        session.clear()
        return jsonify({"ok": True})

    return app


app = create_app()
```

- [ ] **Step 4: Ověřit, že testy prošly**

Run: `python3 -m pytest tests/test_auth.py -v`
Expected: PASS (4 testy).

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_auth.py
git commit -m "Backend: Flask app factory + login/logout se sdíleným heslem"
```

---

### Task 3: State API + servírování frontendu

**Files:**
- Modify: `app.py` (přidat state routy a `/`)
- Create: `tests/test_state.py`

**Interfaces:**
- Consumes: `db.get_state`, `db.put_state` (Task 1); `login_required`, `create_app` (Task 2).
- Produces:
  - `GET /api/state` (login required) → 200 `{"version": int, "data": dict | None}`.
  - `PUT /api/state` (login required), body `{"version": int, "data": dict}` → 200 `{"version": int}`; při neshodě verze → 409 `{"version": int, "data": dict | None, "conflict": true}`; při chybějícím/špatném vstupu → 400.
  - `GET /` → obsah `index.html` (bez auth; auth řeší overlay ve frontendu voláním `/api/state`).

- [ ] **Step 1: Napsat padající testy state API**

Create `tests/test_state.py`:

```python
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
```

- [ ] **Step 2: Ověřit, že testy padají**

Run: `python3 -m pytest tests/test_state.py -v`
Expected: FAIL — 404 na `/api/state` a `/` (routy neexistují).

- [ ] **Step 3: Přidat state routy a `/` do create_app()**

V `app.py`, uvnitř `create_app()`, **za** routu `logout` a **před** `return app`, vlož:

```python
    @app.get("/api/state")
    @login_required
    def get_state():
        return jsonify(db.get_state())

    @app.put("/api/state")
    @login_required
    def put_state():
        body = request.get_json(silent=True) or {}
        data = body.get("data")
        version = body.get("version")
        if not isinstance(data, dict) or not isinstance(version, int):
            abort(400)
        new_version = db.put_state(data, version)
        if new_version is None:
            return jsonify({**db.get_state(), "conflict": True}), 409
        return jsonify({"version": new_version})

    @app.get("/")
    def index():
        return send_file("index.html")
```

- [ ] **Step 4: Ověřit, že testy prošly**

Run: `python3 -m pytest tests/test_state.py -v`
Expected: PASS (6 testů).

- [ ] **Step 5: Spustit celou sadu**

Run: `python3 -m pytest -v`
Expected: PASS (všech 15 testů z Task 1–3).

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_state.py
git commit -m "Backend: GET/PUT /api/state s optimistickým zámkem + servírování index.html"
```

---

### Task 4: Frontend — persistence přes API + přihlašovací overlay

**Files:**
- Modify: `index.html`

**Interfaces:**
- Consumes: `GET/PUT /api/state`, `POST /api/login` (Task 2–3).
- Produces: žádné pro jiné tasky (koncový uživatelský frontend). Interně: globální `STATE_VERSION`, async `boot()`, `apiSave()`, přepsané `save()`.

> **Poznámka k TDD:** frontend je jeden HTML soubor bez JS test runneru (Global Constraint). Chování ověřujeme integračně přes běžící server a prohlížeč (Step 7) + guard grep testem (Step 5). Nezavádět JS framework.

- [ ] **Step 1: Přepsat bootstrap a persistenci**

V `index.html` nahraď blok (aktuálně řádky ~298–301):

```javascript
let S=load();
function load(){ try{const raw=localStorage.getItem("jezdecka_skola_v8"); if(raw) return JSON.parse(raw);}catch(e){} return demoData(); }
function save(){ try{localStorage.setItem("jezdecka_skola_v8",JSON.stringify(S));}catch(e){} }
```

za:

```javascript
let S={horses:[],riders:[],slots:[],assignments:[]};
let STATE_VERSION=0;
let saveTimer=null, saveInFlight=false, saveAgain=false;
const BASE="";

async function apiSave(){
  if(saveInFlight){ saveAgain=true; return; }
  saveInFlight=true;
  try{
    const resp=await fetch(BASE+"/api/state",{method:"PUT",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({version:STATE_VERSION,data:S})});
    if(resp.status===409){
      const cur=await resp.json();
      alert("Data mezitím změnil někdo jiný. Načítám aktuální verzi — zkontroluj prosím poslední úpravu.");
      STATE_VERSION=cur.version; if(cur.data) S=cur.data; renderAll(); return;
    }
    if(resp.status===401){ showLogin(); return; }
    if(resp.ok){ STATE_VERSION=(await resp.json()).version; }
  }catch(e){ /* offline: zůstává v paměti, uloží se dalším savem */ }
  finally{
    saveInFlight=false;
    if(saveAgain){ saveAgain=false; apiSave(); }
  }
}
function save(){ clearTimeout(saveTimer); saveTimer=setTimeout(apiSave,400); }
```

- [ ] **Step 2: Přidat přihlašovací overlay do markupu**

V `index.html` hned za otevírací `<body>` vlož:

```html
<div id="loginOverlay" style="position:fixed;inset:0;background:#f5f2ec;display:none;align-items:center;justify-content:center;z-index:100">
  <form id="loginForm" style="background:#fff;padding:28px;border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,.2);display:flex;flex-direction:column;gap:12px;min-width:280px">
    <h2 style="margin:0 0 4px">🐴 Jezdecká škola</h2>
    <label style="font-size:13px;color:#7d7468">Heslo</label>
    <input type="password" id="loginPw" autofocus style="padding:10px;border:1px solid #e4ddd2;border-radius:8px;font:inherit">
    <div id="loginErr" style="color:#b3543f;font-size:13px;display:none">Špatné heslo.</div>
    <button type="submit" style="background:#7a5c3e;color:#fff;border:0;padding:10px;border-radius:9px;cursor:pointer;font:inherit">Přihlásit</button>
  </form>
</div>
```

- [ ] **Step 3: Přidat login logiku + async boot**

V `index.html` nahraď koncový bootstrap (aktuálně řádky ~694–695):

```javascript
function renderAll(){ renderSched(); renderHorses(); renderRiders(); }
renderAll();
```

za:

```javascript
function renderAll(){ renderSched(); renderHorses(); renderRiders(); }

function showLogin(){ document.getElementById("loginOverlay").style.display="flex"; }
function hideLogin(){ document.getElementById("loginOverlay").style.display="none"; }

async function loadState(){
  const resp=await fetch(BASE+"/api/state");
  if(resp.status===401){ showLogin(); return false; }
  const st=await resp.json();
  STATE_VERSION=st.version;
  if(st.data){ S=st.data; }
  else { S=demoData(); await apiSave(); }
  hideLogin(); renderAll(); return true;
}

document.getElementById("loginForm").onsubmit=async e=>{
  e.preventDefault();
  const pw=document.getElementById("loginPw").value;
  const resp=await fetch(BASE+"/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:pw})});
  if(resp.ok){ document.getElementById("loginErr").style.display="none"; await loadState(); }
  else { document.getElementById("loginErr").style.display="block"; }
};

async function boot(){ await loadState(); }
boot();
```

- [ ] **Step 4: Ošetřit „Obnovit ukázková data" (musí uložit na server)**

Ověř, že handler `resetBtn` (řádek ~693) po `S=demoData()` volá `save()` — to už dělá a `save()` je teď server-side. Žádná změna kódu, jen potvrď grepem v dalším kroku, že v souboru není žádné zbylé `localStorage.setItem`/`localStorage.getItem` pro klíč stavu.

- [ ] **Step 5: Guard test — žádná localStorage persistence stavu**

Run:
```bash
cd ~/Documents/Claude/jezdecka-skola && ! grep -n "localStorage" index.html && echo "OK: localStorage odstraněn"
```
Expected: vypíše `OK: localStorage odstraněn` (žádný výskyt). Pokud grep něco najde, odstraň zbylé použití.

- [ ] **Step 6: Syntax check JS**

Run:
```bash
node -e "const s=require('fs').readFileSync('index.html','utf8');const m=s.match(/<script>([\s\S]*)<\/script>/);new Function(m[1]);console.log('JS OK')"
```
Expected: `JS OK`.

- [ ] **Step 7: Integrační ověření v prohlížeči**

```bash
cd ~/Documents/Claude/jezdecka-skola
SECRET_KEY=dev-secret APP_PASSWORD=kobyla DB_PATH=./dev.db BACKUP_DIR=./backups \
  python3 -m gunicorn app:app --bind 127.0.0.1:8777 &
```
Otevři `http://127.0.0.1:8777/` a ověř ručně:
1. Zobrazí se přihlašovací overlay. Špatné heslo → „Špatné heslo."; heslo `kobyla` → overlay zmizí, načte se rozvrh s ukázkovými daty.
2. Přesuň koně / posaď jezdce. Obnov stránku (F5) → změna přetrvává (načte se z DB, ne z demoData).
3. Otevři druhé okno/prohlížeč, přihlas se, uprav a ulož → v prvním okně další úprava vyvolá hlášku o konfliktu a přenačte.
4. Ukonči server (`kill %1`) a smaž `./dev.db` + `./backups` (`rm -f dev.db; rm -rf backups`) — dev artefakty.

- [ ] **Step 8: Commit**

```bash
git add index.html
git commit -m "Frontend: persistence přes /api/state + přihlašovací overlay + řešení konfliktu verzí"
```

---

### Task 5: Deploy konfigurace (Railway)

**Files:**
- Create: `Procfile`
- Create: `runtime.txt`
- Create: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Consumes: `app:app` (Task 2).
- Produces: nasaditelný projekt — Railway spustí `gunicorn app:app`, SQLite na volume `/data`.

- [ ] **Step 1: Procfile**

Create `Procfile`:

```
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4
```

- [ ] **Step 2: runtime.txt**

Create `runtime.txt`:

```
python-3.11.9
```

- [ ] **Step 3: .env.example**

Create `.env.example`:

```
# Zkopíruj do .env pro lokální běh (nebo nastav jako Railway Variables)
SECRET_KEY=zmen-me-na-nahodny-retezec
APP_PASSWORD=zmen-me-heslo-do-appky
DB_PATH=./dev.db
BACKUP_DIR=./backups
# Na produkci (https) zapni Secure cookie:
COOKIE_SECURE=0
```

- [ ] **Step 4: Lokální smoke test gunicornu**

Run:
```bash
cd ~/Documents/Claude/jezdecka-skola
SECRET_KEY=dev APP_PASSWORD=dev DB_PATH=./dev.db python3 -m gunicorn app:app --bind 127.0.0.1:8778 &
sleep 2 && curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8778/api/ping && kill %1
rm -f dev.db
```
Expected: vypíše `200`.

- [ ] **Step 5: README — sekce Fáze 2**

Do `README.md` přidej sekci:

````markdown
## Fáze 2 — backend (Flask + SQLite)

### Lokální běh
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # vyplň SECRET_KEY a APP_PASSWORD
export $(grep -v '^#' .env | xargs)
gunicorn app:app --bind 127.0.0.1:8777
# http://127.0.0.1:8777/
```

### Deploy na Railway
1. Vytvoř projekt z tohoto GitHub repa (New Project → Deploy from GitHub repo).
2. **Variables** nastav: `SECRET_KEY` (náhodný řetězec), `APP_PASSWORD` (heslo do appky), `DB_PATH=/data/skola.db`, `BACKUP_DIR=/data/backups`, `COOKIE_SECURE=1`.
3. **Volume:** přidej Volume mountnutý na `/data` (perzistence SQLite napříč deployi).
4. Railway detekuje `Procfile` a `requirements.txt` a spustí `gunicorn app:app`.
5. Data se seedují z ukázkového rozpisu při prvním otevření appky (nebo tlačítkem „Obnovit ukázková data").

Zálohy: každý zápis ukládá časovanou JSON kopii do `BACKUP_DIR` (posledních 30).
````

- [ ] **Step 6: Commit**

```bash
git add Procfile runtime.txt .env.example README.md
git commit -m "Deploy: Procfile, runtime, .env.example + README pro Railway"
```

---

## Self-Review

**Spec coverage** (proti `docs/superpowers/specs/2026-08-30-jezdecka-skola-design.md`, Fáze 2):
- „Flask + SQLite, sdílené heslo, data na serveru" → Task 1 (SQLite), Task 2 (heslo/session), Task 3 (state API), Task 4 (frontend). ✓
- „Frontend zůstává jeden soubor, localStorage → API" → Task 4. ✓
- Datový model (horses/riders vč. pref+want / slots / assignments+regular) → uchován 1:1 jako JSON blob, žádná ztráta polí (Task 1 round-trip testy). ✓
- „Výjimky z týdenní šablony (přesun/zrušení na konkrétní datum)" — **záměrně mimo rozsah tohoto plánu.** Spec je řadí do Fáze 2, ale jsou to samostatný subsystém (kalendář konkrétních dat) nad rámec „přenést prototyp na server". Doporučení: samostatný spec+plán (Fáze 2b) po nasazení tohoto backendu. Zaznamenat uživateli při handoffu.
- Deploy (Railway) → Task 5. ✓

**Placeholder scan:** žádné „TODO/TBD/add error handling" — každý krok má reálný kód. ✓

**Type consistency:**
- `db.get_state()` vrací `{"version", "data"}` — konzumováno v `app.py` GET (přímo `jsonify`) i v 409 větvi (`{**db.get_state(), "conflict": True}`). ✓
- `db.put_state(data, expected_version) -> int | None` — `None` větev → 409 v `app.py`. ✓
- Frontend `STATE_VERSION` ↔ `{"version"}` z GET/PUT; `S` ↔ `{"data"}`. ✓
- `create_app()` název konzistentní napříč Task 2/3 a v conftest fixture. ✓

---

## Execution Handoff

Po uložení plánu nabídnu volbu spuštění (viz níže).
