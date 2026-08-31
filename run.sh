#!/usr/bin/env bash
# Spuštění Jezdecké školy lokálně. Data se ukládají do ./skola.db (přežijí restart).
set -euo pipefail
cd "$(dirname "$0")"

# 1) venv + závislosti
if [ ! -d venv ]; then
  echo "Vytvářím virtuální prostředí…"
  python3 -m venv venv
fi
./venv/bin/pip install -q -r requirements.txt

# 2) .env — při prvním spuštění ho vytvoříme s vygenerovaným SECRET_KEY
if [ ! -f .env ]; then
  cp .env.example .env
  SK="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  python3 - "$SK" <<'PY'
import sys, re, pathlib
sk = sys.argv[1]
p = pathlib.Path(".env")
t = re.sub(r'^SECRET_KEY=.*$', f'SECRET_KEY={sk}', p.read_text(), flags=re.M)
p.write_text(t)
PY
  echo ""
  echo "✅ Vytvořil jsem soubor .env s náhodným SECRET_KEY."
  echo "▶  Otevři .env a nastav APP_PASSWORD=tvoje-heslo, pak spusť ./run.sh znovu."
  exit 0
fi

# 3) načti .env a zkontroluj heslo
set -a; source .env; set +a
if [ -z "${APP_PASSWORD:-}" ] || [ "${APP_PASSWORD}" = "zmen-me-heslo-do-appky" ]; then
  echo "⚠  V .env není nastavené APP_PASSWORD. Otevři .env a doplň heslo."
  exit 1
fi

export DB_PATH="${DB_PATH:-./skola.db}"
export BACKUP_DIR="${BACKUP_DIR:-./backups}"
PORT="${PORT:-8777}"

echo ""
echo "🐴 Jezdecká škola běží na  →  http://127.0.0.1:${PORT}/"
echo "   (Ctrl+C ukončí. Data: ${DB_PATH})"
echo ""
exec ./venv/bin/python -m gunicorn app:app --bind 127.0.0.1:"${PORT}" --workers 1 --threads 4
