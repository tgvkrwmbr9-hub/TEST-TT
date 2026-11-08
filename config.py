import os
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
def _e(k, d=""):
    return os.getenv(k, d).strip().strip('"').strip("'").strip()


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
