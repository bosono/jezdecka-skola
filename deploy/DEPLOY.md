# Nasazení na Hetzner server (188.245.223.244 / alias `bosono`)

Server běží Docker + Traefik (spravuje IT / David Navrátil). Uživatel `jarda` nemá
`sudo` ani přístup k Dockeru → **první nasazení musí udělat IT**, další update kódu
už zvládne Jarda sám přes rsync.

Model je stejný jako `melody-dashboard`: kód žije v `/home/jarda/jezdecka-skola/`,
bind-mountuje se do kontejneru, gunicorn běží s `--reload`. Data (SQLite + zálohy)
jsou v odděleném Docker volume, takže přežijí rebuild i redeploy.

---

## A) Jednorázově — IT (David)

### 1. DNS
Vytvořit A záznam `jezdecka.stratcore.cz` → `188.245.223.244`
(nebo jiná subdoména — pak upravit `Host(...)` v compose snippetu).

### 2. Kód na server
Jarda nahraje kód do `/home/jarda/jezdecka-skola/` (viz část B). Ověřit že tam je
`Dockerfile`, `app.py`, `seed.json`.

### 3. Přidat službu do compose
Do `/srv/bosono-app/docker-compose.yml` vložit obsah
[`docker-compose.snippet.yml`](docker-compose.snippet.yml) jako novou službu
(vedle `melody-dashboard`) a do závěrečného `volumes:` bloku přidat
`jezdecka_skola_data:`.

**Před spuštěním nastavit `APP_PASSWORD`** (heslo, které dostane jezdecká škola).
`SECRET_KEY` je už vygenerovaný v snippetu.

### 4. Build + start
```bash
cd /srv/bosono-app
docker compose build jezdecka-skola
docker compose up -d jezdecka-skola
```
Traefik si sám vyžádá Let's Encrypt certifikát. Za ~30 s:
```bash
curl -s https://jezdecka.stratcore.cz/api/ping   # → {"ok": true}
```

Prázdná DB se při prvním startu naplní z `seed.json` (12 koní, 20 lekcí, 44 jezdců).

---

## B) Update kódu — Jarda sám (rsync, bez IT)

```bash
rsync -avz --delete \
  --exclude='.git' --exclude='venv' --exclude='__pycache__' \
  --exclude='.env' --exclude='skola.db' --exclude='backups' \
  --exclude='.pytest_cache' \
  /Users/jaroslavbednar/Documents/Claude/jezdecka-skola/ \
  jarda@bosono:/home/jarda/jezdecka-skola/
```

- **Python / HTML změny:** gunicorn `--reload` je aplikuje sám, nic dalšího netřeba.
- **Změna `requirements.txt`:** napsat IT → `docker compose build jezdecka-skola && docker compose up -d jezdecka-skola`.
- ⚠ VŽDY alias `bosono`, nikdy přímou IP (fail2ban → ban 15–30 min).

### Aktualizace připravených dat (seed)
`seed.json` se použije jen na **prázdnou** DB. Když už appka běží a chci přepsat
data novým seedem:
```bash
ssh bosono 'docker exec jezdecka-skola python -c "import json,db; db.put_state(json.load(open(\"/app/seed.json\")), db.get_state()[\"version\"])"'
```
(nebo prostě upravit data přímo v appce — ta je teď zdroj pravdy)

---

## C) Zálohy

Každý zápis ukládá časovanou JSON kopii do `/data/backups` (posledních 30).
Stáhnout poslední:
```bash
ssh bosono 'docker exec jezdecka-skola sh -c "ls -t /data/backups | head -1"'
ssh bosono 'docker cp jezdecka-skola:/data/backups/<soubor> -' > zaloha.json
```

---

## D) SuperSaaS (později)

Až budou klíče, doplnit do `environment:` v compose:
`SUPERSAAS_API_KEY`, `SUPERSAAS_SCHEDULE_ID`, `SUPERSAAS_ACCOUNT`, `SUPERSAAS_SLOT_MINUTES`.
Bez nich je odeslání do rezervačního systému jen náhled (dry-run).
