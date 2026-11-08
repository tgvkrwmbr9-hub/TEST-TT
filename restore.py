"""Restauration : python3 restore.py            -> liste les sauvegardes
                 python3 restore.py NOM.db.gz  -> restaure (arrête le bot avant)"""
import gzip
import shutil
import sqlite3
import sys
import time

from config import BACKUPS, DB_PATH


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
    tmp = DB_PATH.with_name(DB_PATH.name + ".restore")
    with gzip.open(src, "rb") as f, open(tmp, "wb") as g:
        shutil.copyfileobj(f, g)
    c = sqlite3.connect(tmp)
    ok = c.execute("PRAGMA integrity_check").fetchone()[0]
    c.close()
    if ok != "ok":
        tmp.unlink()
        sys.exit("Sauvegarde invalide, rien n'a été modifié.")
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, BACKUPS / f"avant-restauration-{time.strftime('%Y%m%d-%H%M%S')}.db")
    for s in ("-wal", "-shm"):
        p = DB_PATH.with_name(DB_PATH.name + s)
        if p.exists():
            p.unlink()
    tmp.replace(DB_PATH)
    print("Base restaurée depuis", src.name, "(copie de l'ancienne base conservée dans backups/)")


if __name__ == "__main__":
    main()
