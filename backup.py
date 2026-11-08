"""Sauvegarde quotidienne : base SQLite (copie cohérente à chaud) + PDF et couvertures."""
import gzip
import shutil
import sqlite3
import tarfile
import time
from pathlib import Path

from config import BACKUPS, DATA, DB_PATH, KEEP_DAYS


def main():
    BACKUPS.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    tmp = BACKUPS / f"stych-{ts}.db"
    src, dst = sqlite3.connect(DB_PATH), sqlite3.connect(tmp)
    src.backup(dst)  # API officielle SQLite : sûre même pendant que le bot tourne
    ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
    src.close()
    dst.close()
    if ok != "ok":
        tmp.unlink()
        raise SystemExit("Sauvegarde corrompue : " + ok)
    with open(tmp, "rb") as f, gzip.open(str(tmp) + ".gz", "wb") as g:
        shutil.copyfileobj(f, g)
    tmp.unlink()
    if (DATA / "storage").exists():
        with tarfile.open(BACKUPS / f"fichiers-{ts}.tar.gz", "w:gz") as t:
            t.add(DATA / "storage", arcname="storage")
    cutoff = time.time() - KEEP_DAYS * 86400
    for f in BACKUPS.glob("*"):
        if f.is_file() and f.stat().st_mtime < cutoff and not f.name.startswith("avant-restauration"):
            f.unlink()
    print("Sauvegarde OK :", ts)
    return Path(str(tmp) + ".gz")


if __name__ == "__main__":
    main()
