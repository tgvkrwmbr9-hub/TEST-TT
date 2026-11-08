"""Restauration : python3 restore.py            -> liste les sauvegardes
                 python3 restore.py NOM.db.gz  -> restaure (arrête le bot avant)
Sur Railway : envoie le fichier .db.gz au bot avec la légende /restore."""
import gzip
import shutil
import sqlite3
import sys
import time
from pathlib import Path

from config import BACKUPS, DB_PATH


def restore_file(src: Path):
    src = Path(src)
    tmp = DB_PATH.with_name(DB_PATH.name + ".restore")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if src.name.endswith(".gz"):
        with gzip.open(src, "rb") as f, open(tmp, "wb") as g:
            shutil.copyfileobj(f, g)
    else:
        shutil.copy2(src, tmp)
    try:
        c = sqlite3.connect(tmp)
        ok = c.execute("PRAGMA integrity_check").fetchone()[0]
        c.execute("SELECT 1 FROM users LIMIT 1")
        c.close()
    except sqlite3.DatabaseError:
        ok = "invalide"
    if ok != "ok":
        tmp.unlink(missing_ok=True)
        raise ValueError("Sauvegarde invalide, rien n'a été modifié.")
    BACKUPS.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, BACKUPS / f"avant-restauration-{time.strftime('%Y%m%d-%H%M%S')}.db")
    for s in ("-wal", "-shm"):
        p = DB_PATH.with_name(DB_PATH.name + s)
        if p.exists():
            p.unlink()
    tmp.replace(DB_PATH)


def main():
    if len(sys.argv) < 2:
        print("Sauvegardes disponibles :")
        for f in sorted(BACKUPS.glob("stych-*.db.gz")):
            print("  ", f.name)
        print("\nUsage : python3 restore.py NOM_DU_FICHIER   (arrête d'abord le bot)")
        return
    src = BACKUPS / sys.argv[1]
    if not src.exists():
        sys.exit("Fichier introuvable")
    try:
        restore_file(src)
    except ValueError as e:
        sys.exit(str(e))
    print("Base restaurée depuis", src.name, "(ancienne base conservée dans backups/)")


if __name__ == "__main__":
    main()
