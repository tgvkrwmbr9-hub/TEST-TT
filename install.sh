#!/usr/bin/env bash
# Installation complète sur Ubuntu/Debian : sudo bash deploy/install.sh
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Lance avec sudo"; exit 1; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"; DEST=/opt/stych_tyny
[ -f "$SRC/.env" ] || { echo "Crée d'abord .env :  cp .env.example .env && nano .env"; exit 1; }
apt-get update -y
apt-get install -y python3 python3-venv python3-pip sqlite3 rsync unzip
id stych >/dev/null 2>&1 || useradd --system --home "$DEST" --shell /usr/sbin/nologin stych
mkdir -p "$DEST/data"
rsync -a --exclude data --exclude venv --exclude .env --exclude .git "$SRC/" "$DEST/"
[ -f "$DEST/.env" ] || cp "$SRC/.env" "$DEST/.env"
python3 -m venv "$DEST/venv"
"$DEST/venv/bin/pip" install --upgrade pip
"$DEST/venv/bin/pip" install -r "$DEST/requirements.txt"
chown -R stych:stych "$DEST"; chmod 600 "$DEST/.env"; chmod 700 "$DEST/data"
cp "$DEST"/deploy/*.service "$DEST"/deploy/*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now stych-tyny.service stych-backup.timer
echo "OK. Vérifie : sudo systemctl status stych-tyny"
