#!/usr/bin/env bash
# Mise à jour sans perte : sauvegarde, remplace le code (jamais data/ ni .env), redémarre.
# Usage : depuis le dossier du NOUVEAU code :  sudo bash deploy/update.sh
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"; DEST=/opt/stych_tyny
sudo -u stych "$DEST/venv/bin/python" "$DEST/backup.py"
rsync -a --exclude data --exclude venv --exclude .env --exclude .git "$SRC/" "$DEST/"
"$DEST/venv/bin/pip" install -r "$DEST/requirements.txt"
chown -R stych:stych "$DEST"
systemctl restart stych-tyny
echo "Mise à jour terminée. Données conservées."
