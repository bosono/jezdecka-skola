# Jezdecká škola — Backend (Fáze 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Přidat k existujícímu single-file prototypu (`index.html`) tenký Flask backend, který ukládá data serverově místo do localStorage, chrání je jedním sdíleným heslem a je nasaditelný na Railway.

**Architecture:** Aplikace má jeden sdílený dataset (celý objekt `S = {horses, riders, slots, assignments}`). Backend ho drží jako jeden JSON blob v SQLite (tabulka `state`, jeden řádek) s celočíselnou `version` pro optimistický zámek. Dvě chráněné operace: `GET /api/state` (načíst) a `PUT /api/state` (uložit s kontrolou verze). Frontend zůstává jeden soubor — mění se pouze `load()`/`save()` na `fetch` a přibývá přihlašovací overlay. Datová vrstva je izolovaná v `db.py`, takže pozdější přechod na Postgres je malá změna.

**Tech Stack:** Python 3.11+, Flask 3.x, gunicorn (produkce), SQLite (stdlib `sqlite3`, bez ORM), pytest. SuperSaaS klient přes stdlib `urllib` (bez nové závislosti). Frontend beze změny stacku (vanilla JS v `index.html`).

**SuperSaaS (rezervační systém) — rozsah v tomto plánu:** Připravit kompletní kód napojení tak, aby fungoval bez klíčů v režimu **dry-run** (náhled toho, co by se zapsalo), a živý zápis se odemkl až po doplnění env klíčů. Push vždy zhmotní týdenní šablonu na konkrétní kalendářní týden (zadané pondělní datum) → SuperSaaS rezervace s reálnými `start`/`finish`. Podporuje odeslání jednoho dne i celého týdne; whole-week/day push je idempotentní (smaže rozsah a zapíše čistě). Nejasnost „30min sloty vs. 1 lekce = 1 rezervace" je řešena přepínačem `SUPERSAAS_SLOT_MINUTES`.

## Global Constraints

- **Jazyk UI i hlášek:** čeština (frontend i chybové texty viditelné uživateli).
- **Autentizace:** jedno sdílené heslo z env `APP_PASSWORD`, session cookie podepsaná `SECRET_KEY` (env). Žádné uživatelské účty.
- **Databáze:** SQLite, cesta z env `DB_PATH` (default `skola.db`). Bez ORM, jen stdlib `sqlite3`.
- **Závislosti minimální:** pouze `flask`, `gunicorn`. Nic dalšího do `requirements.txt` bez důvodu.
- **Frontend zůstává jeden soubor** `index.html` — nerozbíjet do modulů, neintrodukovat build krok ani JS test runner.
- **Deploy:** Railway, SQLite na perzistentním volume mountnutém na `/data` (`DB_PATH=/data/skola.db`).
- **Konkurence:** optimistický zámek přes `version`; poslední zapisující s neaktuální verzí dostane 409 a přenačte.
- **DB env se čte za běhu (uvnitř funkcí), ne při importu** — kvůli testovatelnosti s dočasnou DB.
- **SuperSaaS env:** `SUPERSAAS_API_KEY`, `SUPERSAAS_SCHEDULE_ID` (obojí povinné pro živý zápis), `SUPERSAAS_ACCOUNT` (volitelné, jen popisek), `SUPERSAAS_SLOT_MINUTES` (volitelné; prázdné = 1 rezervace na lekci, `30` = lekce rozsekaná na 30min bloky). Env se čte za běhu uvnitř funkcí.
- **SuperSaaS bez klíčů = dry-run:** endpoint push bez nakonfigurovaných klíčů vrací jen náhled zhmotněných rezervací (nikdy neselže kvůli chybějícímu klíči). Živý zápis běží jen když `is_configured()`.
- **SuperSaaS HTTP přes stdlib `urllib`** s injektovatelným `transport` callablem, aby testy běžely bez sítě i bez klíče.

---

## File Structure

```
jezdecka-skola/
  index.html          # MODIFY: load()/save() → API, login overlay, verze; SuperSaaS toolbar
  db.py               # CREATE: SQLite state store (init_db, get_state, put_state, backup)
  app.py              # CREATE: Flask app factory, auth, state API, SuperSaaS push, servírování index.html
  supersaas.py        # CREATE: zhmotnění týdenní šablony → rezervace + HTTP klient (urllib)
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
    test_supersaas.py # CREATE: testy zhmotnění týdne + klienta s fake transportem
  README.md           # MODIFY: sekce Fáze 2 – lokální běh + deploy Railway
  docs/superpowers/...
```

**Zodpovědnosti:**
- `db.py` — veškerá práce s SQLite a se soubory záloh. Nezná Flask.
- `app.py` — HTTP vrstva: routy, session, autentizace, validace vstupu, servírování `index.html`. Data deleguje na `db.py`, SuperSaaS na `supersaas.py`.
- `supersaas.py` — čistá transformace týdenní šablony na rezervace (`week_bookings`, `week_range`) + HTTP klient (`SuperSaasClient`, `client_from_env`, `is_configured`). Nezná Flask.
- `index.html` — UI a in-memory model; persistence přes `fetch`; toolbar pro odeslání do SuperSaaS.

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
# SuperSaaS (rezervační systém) — doplň, až budou klíče; bez nich jede jen dry-run náhled:
SUPERSAAS_API_KEY=
SUPERSAAS_SCHEDULE_ID=
SUPERSAAS_ACCOUNT=
# Prázdné = 1 rezervace na lekci; 30 = lekce rozsekaná na 30min bloky:
SUPERSAAS_SLOT_MINUTES=
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

### Task 6: SuperSaaS — zhmotnění týdenní šablony na rezervace (čistá logika)

**Files:**
- Create: `supersaas.py`
- Create: `tests/test_supersaas.py`

**Interfaces:**
- Produces:
  - `supersaas.week_bookings(state: dict, week_start: date, days=None, slot_minutes=None) -> list[dict]` — zhmotní týdenní šablonu na konkrétní týden. `week_start` = datum pondělí (den index 0). `days` = iterable indexů 0–6 nebo `None` (celý týden). `slot_minutes=None` → jedna rezervace na lekci; int → rozsekání na bloky. Vrací seřazený seznam `{"day": int, "start": "YYYY-MM-DD HH:MM:SS", "finish": ..., "full_name": str}`.
  - `supersaas.week_range(week_start: date, days=None) -> tuple[str, str]` — `(from, to)` řetězce ohraničující rozsah dat pro smazání/čtení.

- [ ] **Step 1: Napsat padající testy čisté logiky**

Create `tests/test_supersaas.py`:

```python
from datetime import date
import supersaas


STATE = {
    "horses": [{"id": "h1", "name": "Dally", "pony": False},
               {"id": "h2", "name": "Sargas", "pony": True}],
    "riders": [{"id": "r1", "name": "Adéla Nováková"}],
    "slots": [
        {"id": "s1", "day": 0, "from": "16:00", "to": "17:00", "type": "skup", "coach": "Martina"},
        {"id": "s2", "day": 2, "from": "19:00", "to": "20:00", "type": "skok", "coach": "Veronika"},
    ],
    "assignments": [
        {"slot": "s1", "horse": "h1", "rider": "r1", "regular": True},
        {"slot": "s1", "horse": "h2", "rider": None, "regular": False},
    ],
}
MONDAY = date(2026, 8, 31)  # pondělí


def test_week_bookings_whole_week_concrete_dates():
    out = supersaas.week_bookings(STATE, MONDAY)
    assert len(out) == 2
    assert out[0]["start"] == "2026-08-31 16:00:00"
    assert out[0]["finish"] == "2026-08-31 17:00:00"
    # středa = pondělí + 2
    assert out[1]["start"] == "2026-09-02 19:00:00"


def test_week_bookings_full_name_has_label_and_mounts():
    out = supersaas.week_bookings(STATE, MONDAY, days=[0])
    assert "Skupinová" in out[0]["full_name"]
    assert "Martina" in out[0]["full_name"]
    assert "Dally" in out[0]["full_name"]


def test_week_bookings_single_day_filter():
    out = supersaas.week_bookings(STATE, MONDAY, days=[2])
    assert len(out) == 1
    assert out[0]["start"].startswith("2026-09-02")


def test_week_bookings_slot_minutes_splits_lesson():
    out = supersaas.week_bookings(STATE, MONDAY, days=[0], slot_minutes=30)
    assert len(out) == 2  # 16:00-17:00 → dva 30min bloky
    assert out[0]["start"] == "2026-08-31 16:00:00"
    assert out[0]["finish"] == "2026-08-31 16:30:00"
    assert out[1]["start"] == "2026-08-31 16:30:00"
    assert out[1]["finish"] == "2026-08-31 17:00:00"


def test_week_range_whole_week():
    frm, to = supersaas.week_range(MONDAY)
    assert frm == "2026-08-31 00:00:00"
    assert to == "2026-09-07 00:00:00"
```

- [ ] **Step 2: Ověřit, že testy padají**

Run: `python3 -m pytest tests/test_supersaas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'supersaas'`.

- [ ] **Step 3: Implementovat čistou logiku v supersaas.py**

Create `supersaas.py`:

```python
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta

TYPE_NAMES = {
    "skup": "Skupinová",
    "kaval": "Kavaletová",
    "komb": "Kombinovaná",
    "skok": "Skoková",
    "souk": "Soukromá",
}


def _parse_time(t):
    h, m = t.split(":")
    return time(int(h), int(m))


def _lesson_label(slot):
    name = TYPE_NAMES.get(slot.get("type"), slot.get("type", ""))
    coach = slot.get("coach")
    return name + (f" ({coach})" if coach else "")


def _lesson_mounts(slot, assignments, horses, riders):
    parts = []
    for a in assignments:
        if a.get("slot") != slot["id"]:
            continue
        h = horses.get(a.get("horse"))
        hn = h["name"] if h else "?"
        r = riders.get(a.get("rider"))
        parts.append(hn + (f"/{r['name'].split(' ')[0]}" if r else ""))
    return ", ".join(parts)


def _split(start_dt, finish_dt, slot_minutes):
    if not slot_minutes:
        return [(start_dt, finish_dt)]
    out = []
    cur = start_dt
    step = timedelta(minutes=slot_minutes)
    while cur < finish_dt:
        nxt = min(cur + step, finish_dt)
        out.append((cur, nxt))
        cur = nxt
    return out


def week_bookings(state, week_start, days=None, slot_minutes=None):
    horses = {h["id"]: h for h in state.get("horses", [])}
    riders = {r["id"]: r for r in state.get("riders", [])}
    assignments = state.get("assignments", [])
    day_set = set(range(7)) if days is None else set(days)
    out = []
    for s in state.get("slots", []):
        if s["day"] not in day_set:
            continue
        d = week_start + timedelta(days=s["day"])
        start_dt = datetime.combine(d, _parse_time(s["from"]))
        finish_dt = datetime.combine(d, _parse_time(s["to"]))
        mounts = _lesson_mounts(s, assignments, horses, riders)
        label = _lesson_label(s)
        full_name = label + (f": {mounts}" if mounts else "")
        for cs, cf in _split(start_dt, finish_dt, slot_minutes):
            out.append({
                "day": s["day"],
                "start": cs.strftime("%Y-%m-%d %H:%M:%S"),
                "finish": cf.strftime("%Y-%m-%d %H:%M:%S"),
                "full_name": full_name,
            })
    out.sort(key=lambda b: b["start"])
    return out


def week_range(week_start, days=None):
    ds = sorted(range(7) if days is None else days)
    first = week_start + timedelta(days=ds[0])
    last = week_start + timedelta(days=ds[-1] + 1)
    return first.strftime("%Y-%m-%d 00:00:00"), last.strftime("%Y-%m-%d 00:00:00")
```

- [ ] **Step 4: Ověřit, že testy prošly**

Run: `python3 -m pytest tests/test_supersaas.py -v`
Expected: PASS (5 testů).

- [ ] **Step 5: Commit**

```bash
git add supersaas.py tests/test_supersaas.py
git commit -m "SuperSaaS: zhmotnění týdenní šablony na rezervace (čistá logika + testy)"
```

---

### Task 7: SuperSaaS — HTTP klient (bez klíčů testovatelný)

**Files:**
- Modify: `supersaas.py` (přidat klienta a konfiguraci)
- Modify: `tests/test_supersaas.py` (přidat testy klienta)

**Interfaces:**
- Consumes: `week_bookings`, `week_range` (Task 6).
- Produces:
  - `supersaas.is_configured() -> bool` — `True` když jsou `SUPERSAAS_API_KEY` i `SUPERSAAS_SCHEDULE_ID`.
  - `supersaas.SuperSaasError(status, body)` — výjimka.
  - `supersaas.SuperSaasClient(api_key, schedule_id, base_url="https://www.supersaas.com", transport=None)` — metody `create_booking(booking) -> str|None`, `list_range(from, to) -> list`, `delete_booking(id) -> None`, `replace(bookings, from, to) -> {"deleted": int, "created": int, "ids": list}`. `transport(method, url, headers, data) -> (status:int, body:bytes, headers:dict)` je injektovatelný.
  - `supersaas.client_from_env(transport=None) -> SuperSaasClient`.

- [ ] **Step 1: Napsat padající testy klienta (fake transport)**

Připoj do `tests/test_supersaas.py`:

```python
import supersaas as ss


class FakeTransport:
    def __init__(self):
        self.calls = []
        self.range_result = b"[]"

    def __call__(self, method, url, headers, data):
        self.calls.append((method, url, data))
        if method == "GET":
            return 200, self.range_result, {}
        if method == "POST":
            return 201, b"{}", {"Location": "/api/bookings/999.json"}
        if method == "DELETE":
            return 200, b"", {}
        return 400, b"", {}


def test_client_create_returns_id_from_location():
    t = FakeTransport()
    client = ss.SuperSaasClient("KEY", "42", transport=t)
    bid = client.create_booking({"start": "2026-08-31 16:00:00", "finish": "2026-08-31 17:00:00", "full_name": "Skupinová"})
    assert bid == "999"
    method, url, data = t.calls[0]
    assert method == "POST"
    assert "api_key=KEY" in url


def test_client_replace_deletes_then_creates():
    t = FakeTransport()
    t.range_result = b'[{"id": 111}, {"id": 222}]'
    client = ss.SuperSaasClient("KEY", "42", transport=t)
    bookings = [{"start": "2026-08-31 16:00:00", "finish": "2026-08-31 17:00:00", "full_name": "A"}]
    result = client.replace(bookings, "2026-08-31 00:00:00", "2026-09-07 00:00:00")
    assert result["deleted"] == 2
    assert result["created"] == 1
    methods = [c[0] for c in t.calls]
    assert methods == ["GET", "DELETE", "DELETE", "POST"]


def test_is_configured(monkeypatch):
    monkeypatch.delenv("SUPERSAAS_API_KEY", raising=False)
    monkeypatch.delenv("SUPERSAAS_SCHEDULE_ID", raising=False)
    assert ss.is_configured() is False
    monkeypatch.setenv("SUPERSAAS_API_KEY", "k")
    monkeypatch.setenv("SUPERSAAS_SCHEDULE_ID", "42")
    assert ss.is_configured() is True
```

- [ ] **Step 2: Ověřit, že testy padají**

Run: `python3 -m pytest tests/test_supersaas.py -v`
Expected: FAIL — `AttributeError: module 'supersaas' has no attribute 'SuperSaasClient'`.

- [ ] **Step 3: Implementovat klienta v supersaas.py**

Připoj na konec `supersaas.py`:

```python
class SuperSaasError(Exception):
    def __init__(self, status, body):
        super().__init__(f"SuperSaaS HTTP {status}: {body!r}")
        self.status = status
        self.body = body


def is_configured():
    return bool(os.environ.get("SUPERSAAS_API_KEY") and os.environ.get("SUPERSAAS_SCHEDULE_ID"))


def slot_minutes_from_env():
    v = os.environ.get("SUPERSAAS_SLOT_MINUTES", "").strip()
    return int(v) if v.isdigit() and int(v) > 0 else None


class SuperSaasClient:
    def __init__(self, api_key, schedule_id, base_url="https://www.supersaas.com", transport=None):
        self.api_key = api_key
        self.schedule_id = str(schedule_id)
        self.base_url = base_url.rstrip("/")
        self._transport = transport or self._http

    def _http(self, method, url, headers, data):
        req = urllib.request.Request(url, method=method, headers=headers, data=data)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def _url(self, path, params=None):
        p = dict(params or {})
        p["api_key"] = self.api_key
        return f"{self.base_url}{path}?{urllib.parse.urlencode(p)}"

    def create_booking(self, booking):
        url = self._url("/api/bookings.json")
        payload = {
            "schedule_id": self.schedule_id,
            "booking": {k: booking[k] for k in ("start", "finish", "full_name")},
        }
        status, body, headers = self._transport(
            "POST", url, {"Content-Type": "application/json"}, json.dumps(payload).encode("utf-8")
        )
        if status not in (200, 201):
            raise SuperSaasError(status, body)
        loc = headers.get("Location", "")
        tail = loc.rstrip("/").split("/")[-1]
        return tail.split(".")[0] if tail else None

    def list_range(self, from_dt, to_dt):
        url = self._url(f"/api/range/{self.schedule_id}.json", {"from": from_dt, "to": to_dt})
        status, body, _ = self._transport("GET", url, {}, None)
        if status != 200:
            raise SuperSaasError(status, body)
        return json.loads(body or b"[]")

    def delete_booking(self, booking_id):
        url = self._url(f"/api/bookings/{booking_id}.json", {"schedule_id": self.schedule_id})
        status, body, _ = self._transport("DELETE", url, {}, None)
        if status not in (200, 204):
            raise SuperSaasError(status, body)

    def replace(self, bookings, from_dt, to_dt):
        existing = self.list_range(from_dt, to_dt)
        deleted = 0
        for b in existing:
            bid = b.get("id")
            if bid is not None:
                self.delete_booking(bid)
                deleted += 1
        ids = [self.create_booking(b) for b in bookings]
        return {"deleted": deleted, "created": len(ids), "ids": ids}


def client_from_env(transport=None):
    return SuperSaasClient(
        os.environ["SUPERSAAS_API_KEY"], os.environ["SUPERSAAS_SCHEDULE_ID"], transport=transport
    )
```

- [ ] **Step 4: Ověřit, že testy prošly**

Run: `python3 -m pytest tests/test_supersaas.py -v`
Expected: PASS (8 testů).

- [ ] **Step 5: Commit**

```bash
git add supersaas.py tests/test_supersaas.py
git commit -m "SuperSaaS: HTTP klient (create/list/delete/replace) s injektovatelným transportem"
```

---

### Task 8: SuperSaaS — Flask endpointy push + status

**Files:**
- Modify: `app.py`
- Modify: `tests/test_state.py` (přidat testy SuperSaaS endpointů)

**Interfaces:**
- Consumes: `supersaas.week_bookings`, `supersaas.week_range`, `supersaas.is_configured`, `supersaas.slot_minutes_from_env`, `supersaas.client_from_env` (Task 6–7); `db.get_state`, `login_required` (Task 1–2).
- Produces:
  - `GET /api/supersaas/status` (login required) → `{"configured": bool, "schedule_id": str|None, "slot_minutes": int|None}`.
  - `POST /api/supersaas/push` (login required), body `{"week_start": "YYYY-MM-DD", "days": [int]|null, "dry_run": bool}` → dry-run nebo bez klíčů: `{"configured": bool, "dry_run": true, "count": int, "bookings": [...]}`; živě: `{"configured": true, "dry_run": false, "deleted": int, "created": int, "count": int}`. Neplatné `week_start` → 400.

- [ ] **Step 1: Napsat padající testy endpointů**

Připoj do `tests/test_state.py`:

```python
def test_supersaas_status_default(auth_client):
    resp = auth_client.get("/api/supersaas/status")
    assert resp.status_code == 200
    assert resp.get_json()["configured"] is False


def test_supersaas_push_dry_run_without_keys(auth_client):
    auth_client.put("/api/state", json={"version": 0, "data": {
        "horses": [{"id": "h1", "name": "Dally", "pony": False}],
        "riders": [], "assignments": [{"slot": "s1", "horse": "h1", "rider": None}],
        "slots": [{"id": "s1", "day": 0, "from": "16:00", "to": "17:00", "type": "skup", "coach": "Martina"}],
    }})
    resp = auth_client.post("/api/supersaas/push", json={"week_start": "2026-08-31", "days": None, "dry_run": True})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["configured"] is False
    assert body["dry_run"] is True
    assert body["count"] == 1
    assert body["bookings"][0]["start"] == "2026-08-31 16:00:00"


def test_supersaas_push_bad_date(auth_client):
    resp = auth_client.post("/api/supersaas/push", json={"week_start": "31.8.2026"})
    assert resp.status_code == 400
```

- [ ] **Step 2: Ověřit, že testy padají**

Run: `python3 -m pytest tests/test_state.py -v -k supersaas`
Expected: FAIL — 404 (routy neexistují).

- [ ] **Step 3: Přidat SuperSaaS endpointy + import do app.py**

V `app.py` uprav horní import blok — přidej řádek `from datetime import date` a `import supersaas` k existujícím importům:

```python
from datetime import date, timedelta
```
(řádek `from datetime import timedelta` nahraď tímto) a mezi `import db` přidej:
```python
import supersaas
```

Poté uvnitř `create_app()`, za routu `/` (`index`) a před `return app`, vlož:

```python
    @app.get("/api/supersaas/status")
    @login_required
    def supersaas_status():
        return jsonify({
            "configured": supersaas.is_configured(),
            "schedule_id": os.environ.get("SUPERSAAS_SCHEDULE_ID"),
            "slot_minutes": supersaas.slot_minutes_from_env(),
        })

    @app.post("/api/supersaas/push")
    @login_required
    def supersaas_push():
        body = request.get_json(silent=True) or {}
        try:
            week_start = date.fromisoformat(str(body.get("week_start", "")))
        except ValueError:
            abort(400)
        days = body.get("days")
        dry_run = bool(body.get("dry_run"))
        state = db.get_state().get("data") or {"horses": [], "riders": [], "slots": [], "assignments": []}
        minutes = supersaas.slot_minutes_from_env()
        bookings = supersaas.week_bookings(state, week_start, days=days, slot_minutes=minutes)
        if dry_run or not supersaas.is_configured():
            return jsonify({"configured": supersaas.is_configured(), "dry_run": True,
                            "count": len(bookings), "bookings": bookings})
        from_dt, to_dt = supersaas.week_range(week_start, days)
        result = supersaas.client_from_env().replace(bookings, from_dt, to_dt)
        return jsonify({"configured": True, "dry_run": False, "count": len(bookings), **result})
```

- [ ] **Step 4: Ověřit, že testy prošly**

Run: `python3 -m pytest tests/test_state.py -v -k supersaas`
Expected: PASS (3 testy).

- [ ] **Step 5: Spustit celou sadu**

Run: `python3 -m pytest -v`
Expected: PASS (všech 26 testů z Task 1–8).

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_state.py
git commit -m "SuperSaaS: endpointy /api/supersaas/status a /push (dry-run bez klíčů, živě s klíči)"
```

---

### Task 9: Frontend — tlačítko odeslání do SuperSaaS

**Files:**
- Modify: `index.html`

**Interfaces:**
- Consumes: `GET /api/supersaas/status`, `POST /api/supersaas/push` (Task 8).
- Produces: žádné pro jiné tasky.

> **TDD poznámka:** stejně jako Task 4 — vanilla JS bez runneru, ověřuje se integračně přes běžící server (Step 4).

- [ ] **Step 1: Přidat SuperSaaS toolbar do markupu rozvrhu**

V `index.html`, uvnitř `<div class="board-tools">` (existující blok s tlačítkem „Nový týden"), přidej za `<span class="muted" ...>konkrétní datumy a výjimky – další fáze</span>`:

```html
      <span style="flex:1"></span>
      <label style="font-size:12.5px;display:flex;align-items:center;gap:6px">Týden od
        <input type="date" id="ssWeek" style="padding:5px 8px;border:1px solid #e4ddd2;border-radius:8px;font:inherit"></label>
      <button class="btn sm ghost" id="ssPreview" title="Náhled, co by se zapsalo do SuperSaaS">Náhled SuperSaaS</button>
      <button class="btn sm" id="ssPush" title="Odeslat celý týden do rezervačního systému">Odeslat týden →</button>
```

- [ ] **Step 2: Přidat SuperSaaS logiku do skriptu**

V `index.html` přidej před `boot();` (konec skriptu):

```javascript
function mondayOfThisWeek(){
  const d=new Date(); const day=(d.getDay()+6)%7; d.setDate(d.getDate()-day);
  return d.toISOString().slice(0,10);
}
async function ssPush(dryRun){
  const wk=document.getElementById("ssWeek").value;
  if(!wk){ alert("Vyber pondělní datum týdne."); return; }
  const resp=await fetch(BASE+"/api/supersaas/push",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({week_start:wk,days:null,dry_run:dryRun})});
  if(resp.status===401){ showLogin(); return; }
  if(!resp.ok){ alert("Chyba odeslání do SuperSaaS ("+resp.status+")."); return; }
  const r=await resp.json();
  if(r.dry_run){
    const lines=r.bookings.map(b=>`${b.start.slice(0,16)} — ${b.full_name}`).join("\n")||"(žádné lekce)";
    const note=r.configured?"":"\n\n⚠ SuperSaaS zatím není nakonfigurován (chybí API klíč) — jde jen o náhled.";
    alert(`Náhled ${r.count} rezervací pro týden ${wk}:\n\n${lines}${note}`);
  }else{
    alert(`Odesláno do SuperSaaS: vytvořeno ${r.created}, smazáno ${r.deleted} (týden ${wk}).`);
  }
}
async function ssInit(){
  document.getElementById("ssWeek").value=mondayOfThisWeek();
  const btn=document.getElementById("ssPush");
  try{
    const st=await (await fetch(BASE+"/api/supersaas/status")).json();
    if(!st.configured){ btn.textContent="Odeslat týden (bez klíče)"; btn.title="SuperSaaS není nakonfigurován — funguje jen náhled"; }
  }catch(e){}
  document.getElementById("ssPreview").onclick=()=>ssPush(true);
  btn.onclick=()=>{ if(confirm("Odeslat celý týden do SuperSaaS? Přepíše rezervace v daném rozsahu.")) ssPush(false); };
}
```

A do `loadState()`, hned za `hideLogin();` (před `renderAll()`), přidej volání:

```javascript
  ssInit();
```

- [ ] **Step 3: Syntax check JS**

Run:
```bash
node -e "const s=require('fs').readFileSync('index.html','utf8');const m=s.match(/<script>([\s\S]*)<\/script>/);new Function(m[1]);console.log('JS OK')"
```
Expected: `JS OK`.

- [ ] **Step 4: Integrační ověření**

Spusť server (viz Task 4 Step 7). V appce ověř:
1. V toolbaru rozvrhu je datum (pondělí tohoto týdne), „Náhled SuperSaaS" a „Odeslat týden".
2. „Náhled SuperSaaS" → alert se seznamem rezervací s konkrétními daty + poznámkou, že SuperSaaS není nakonfigurován.
3. Bez klíčů tlačítko odeslání ukazuje „(bez klíče)" a taky jen náhled.

Ukliď dev artefakty (`rm -f dev.db; rm -rf backups`).

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "Frontend: toolbar Odeslat týden do SuperSaaS (náhled + push)"
```

---

## Self-Review

**Spec coverage** (proti `docs/superpowers/specs/2026-08-30-jezdecka-skola-design.md`, Fáze 2):
- „Flask + SQLite, sdílené heslo, data na serveru" → Task 1 (SQLite), Task 2 (heslo/session), Task 3 (state API), Task 4 (frontend). ✓
- „Frontend zůstává jeden soubor, localStorage → API" → Task 4. ✓
- Datový model (horses/riders vč. pref+want / slots / assignments+regular) → uchován 1:1 jako JSON blob, žádná ztráta polí (Task 1 round-trip testy). ✓
- „Výjimky z týdenní šablony (přesun/zrušení na konkrétní datum)" — **záměrně mimo rozsah tohoto plánu.** Spec je řadí do Fáze 2, ale jsou to samostatný subsystém (kalendář konkrétních dat) nad rámec „přenést prototyp na server". Doporučení: samostatný spec+plán (Fáze 2b) po nasazení tohoto backendu. Zaznamenat uživateli při handoffu.
- Deploy (Railway) → Task 5. ✓
- SuperSaaS napojení (poslat den / celý týden, vždy celý týden, nejasnost 30min slotů) → Task 6 (zhmotnění týdne + `slot_minutes` toggle), Task 7 (klient + idempotentní `replace`), Task 8 (endpointy, dry-run bez klíčů), Task 9 (UI). ✓
- „Vždy celý týden" → `week_bookings` bere jeden `week_start` a `replace()` přepíše celý rozsah; `days` umožní i jeden den. ✓
- „Klíče později" → vše testovatelné bez klíčů (fake transport, dry-run); živý zápis gated přes `is_configured()`. ✓

**Placeholder scan:** žádné „TODO/TBD/add error handling" — každý krok má reálný kód. ✓

**Type consistency:**
- `db.get_state()` vrací `{"version", "data"}` — konzumováno v `app.py` GET (přímo `jsonify`) i v 409 větvi (`{**db.get_state(), "conflict": True}`). ✓
- `db.put_state(data, expected_version) -> int | None` — `None` větev → 409 v `app.py`. ✓
- Frontend `STATE_VERSION` ↔ `{"version"}` z GET/PUT; `S` ↔ `{"data"}`. ✓
- `create_app()` název konzistentní napříč Task 2/3 a v conftest fixture. ✓
- `SuperSaasClient(api_key, schedule_id, ...)` — pořadí a názvy argumentů shodné v Task 7 (definice), testech i `client_from_env`. ✓
- `week_bookings(state, week_start, days, slot_minutes)` a `week_range(week_start, days)` — signatury shodné mezi Task 6 (def) a Task 8 (volání v endpointu). ✓
- Booking dict klíče `start/finish/full_name` — produkované `week_bookings` (Task 6), konzumované `create_booking` (Task 7). ✓

## Otevřené rozhodnutí (vyřešit až s klíči + přístupem do SuperSaaS)

1. **1 rezervace na lekci vs. per-jezdec:** plán zapisuje **jednu rezervaci na lekci** (obsazenost haly), `full_name` nese seznam koní/jezdců. Pokud SuperSaaS slouží ke klientské self-rezervaci po místech, bude potřeba varianta „rezervace na jezdce" — malá úprava `week_bookings`.
2. **Granularita slotů:** default 1 rezervace/lekce; `SUPERSAAS_SLOT_MINUTES=30` rozseká na bloky. Ověřit, zda je rozvrh v SuperSaaS *resource* (start/finish) nebo *capacity* (slot_id) — capacity by vyžadovalo mapování `slot_id` (další drobná úprava klienta).
3. **`schedule_id`** konkrétního rozvrhu jezdecké školy — doplnit do env.

---

## Execution Handoff

Po uložení plánu nabídnu volbu spuštění (viz níže).
