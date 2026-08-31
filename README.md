# Jezdecká škola — CRM

Jednoduchý nástroj pro jezdeckou školu: kartotéka jezdců, kartotéka koní (vč. vytíženosti),
párování jezdec–kůň a týdenní rozvrh lekcí s drag&drop.

## Stav

**Fáze 1 — klikací náhled (hotovo).** `index.html` je samostatná stránka bez závislostí,
data se ukládají do `localStorage` prohlížeče. Slouží k odladění workflow a vzhledu.

Otevři přímo:
```bash
open index.html
```
nebo přes lokální server (kvůli konzistenci s budoucím nasazením):
```bash
python3 -m http.server 8777
# http://localhost:8777/index.html
```

### Co náhled umí
- **Jezdci** — jméno, úroveň (začátečník / pokročilý / závodník), preferovaní koně (nápověda),
  kontakt, počet lekcí v týdnu. Filtr podle úrovně, hledání.
- **Koně** — popis, povolené disciplíny, limity (lekcí/den, lekcí/týden, hodin/týden),
  dny volna. Ukazatel vytíženosti (zelená / žlutá / červená).
- **Rozvrh** — týdenní mřížka (dny × čas). Sloty lekcí se přidávají kliknutím do volné buňky.
  Jezdce přetáhneš z panelu do slotu, koně přiřadíš výběrem nebo přetažením na řádek dvojice.
  Měkká varování (nízká úroveň, kůň bez disciplíny, překročený limit, den volna) a tvrdé
  blokace (kolize jezdce/koně ve stejném čase).
- Typy lekcí: skupinové, kavalety, kombinovaná, skoková (poslední tři vyžadují pokročilé).

## Další fáze (plán)

- **Fáze 2 — backend.** Python + Flask + SQLite, jedno sdílené heslo, data na serveru.
  Konkrétní datumy a výjimky z týdenní šablony (přesun/zrušení lekce na daný den).
- **Fáze 3 — nasazení.** GitHub repo (možná pod účtem Bosono) + hosting.

Návrh: `docs/superpowers/specs/2026-08-30-jezdecka-skola-design.md`

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

### Deploy na Hetzner server (bosono) — Docker + Traefik

Kompletní postup: [`deploy/DEPLOY.md`](deploy/DEPLOY.md). První nasazení přes IT
(přidá službu do compose + DNS), další update kódu už Jarda sám přes rsync.
V repu je `Dockerfile`, `gunicorn.conf.py` a hotový compose snippet
[`deploy/docker-compose.snippet.yml`](deploy/docker-compose.snippet.yml).

Prázdná DB se při startu naplní ze `seed.json`, když je nastaveno `SEED_PATH`
(v produkčním compose `SEED_PATH=/app/seed.json`).

### Deploy na Railway (alternativa)
1. Vytvoř projekt z tohoto GitHub repa (New Project → Deploy from GitHub repo).
2. **Variables** nastav: `SECRET_KEY`, `APP_PASSWORD`, `DB_PATH=/data/skola.db`, `BACKUP_DIR=/data/backups`, `SEED_PATH=/app/seed.json`, `COOKIE_SECURE=1`.
3. **Volume:** přidej Volume mountnutý na `/data` (perzistence SQLite napříč deployi).
4. Railway detekuje `Procfile` a `requirements.txt` a spustí `gunicorn app:app`.

Zálohy: každý zápis ukládá časovanou JSON kopii do `BACKUP_DIR` (posledních 30).

SuperSaaS env klíče (`SUPERSAAS_API_KEY`, `SUPERSAAS_SCHEDULE_ID`, …) jsou volitelné — bez nich funguje odeslání do rezervačního systému jen jako náhled (dry-run) a nic se reálně nezapíše.
