import os
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent


def _load_env():
    f = BASE / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()
_ENV = {re.sub(r"[^A-Z0-9_]", "", k.upper()): v for k, v in os.environ.items()}


def _e(k, d=""):
    """Lit une variable en tolérant espaces, casse, guillemets et caractères invisibles dans le nom."""
    v = os.environ.get(k) or _ENV.get(k) or d
    return v.strip().strip('"').strip("'").strip()


BOT_TOKEN = _e("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in _e("ADMIN_ID").replace(" ", "").split(",") if x.strip("\"' ").isdigit() for x in [x.strip("\"' ")]]
ADMIN_USERNAME = _e("ADMIN_USERNAME").lstrip("@")
SUPPORT = _e("SUPPORT_USERNAME").lstrip("@") or ADMIN_USERNAME
STORE = os.getenv("STORE_NAME", "STYCH TYNY")
DATA = Path(os.getenv("DATA_DIR") or os.getenv("RAILWAY_VOLUME_MOUNT_PATH") or BASE / "data")
DB_PATH = Path(os.getenv("DATABASE_PATH", DATA / "stych.db"))
EBOOKS = DATA / "storage" / "ebooks"
COVERS = DATA / "storage" / "covers"
BACKUPS = DATA / "backups"
LOGS = DATA / "logs"
KEEP_DAYS = int(os.getenv("BACKUP_KEEP_DAYS", "14"))

if not BOT_TOKEN or not ADMIN_IDS:  # diagnostic : noms et longueurs seulement, jamais les valeurs
    print("DIAGNOSTIC variables vues :", {k: len(v) for k, v in os.environ.items()
          if any(w in k.upper() for w in ("BOT", "ADMIN", "TOKEN", "SUPPORT", "STORE", "DATA"))}, flush=True)
