"""Test de la couche données (sans Telegram) : python3 tests/test_db.py"""
import asyncio, os, sqlite3, subprocess, sys, tempfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
os.environ["DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(root))
import database as db
from config import BACKUPS, DB_PATH


class U:  # faux utilisateur Telegram
    def __init__(s, i): s.id, s.username, s.first_name = i, f"u{i}", f"User{i}"


async def main():
    db.init(); db.init()  # 2e démarrage : rien n'est écrasé
    await db.upsert_user(U(1)); await db.upsert_user(U(2))
    pid, _ = await db.run("INSERT INTO products(name,price,created_at) VALUES('Guide',1500,?)", (db.now(),))
    o1 = await db.create_order(1, pid, 1500, "crypto:SOL", "A" * 40, None)
    try:
        await db.create_order(2, pid, 1500, "crypto:SOL", "A" * 40, None)
        raise SystemExit("TXID dupliqué accepté !")
    except sqlite3.IntegrityError:
        print("OK  TXID dupliqué refusé")
    assert await db.validate(o1, 99)
    assert await db.validate(o1, 99) is None
    print("OK  double validation bloquée")
    assert (await db.one("SELECT sales FROM products WHERE id=?", (pid,)))["sales"] == 1
    assert await db.one("SELECT 1 x FROM purchases WHERE user_id=1 AND product_id=?", (pid,))
    print("OK  achat enregistré")
    assert not await db.one("SELECT 1 x FROM purchases WHERE user_id=2 AND product_id=?", (pid,))
    print("OK  utilisateur 2 sans accès")
    a = await db.create_order(2, pid, 1500, "crypto:BTC", "B" * 40, None)
    b = await db.create_order(2, pid, 1500, "crypto:ETH", "C" * 40, None)
    r1 = await db.refuse(a, 99); assert r1["strikes"] == 1 and not r1["banned"]
    r2 = await db.refuse(b, 99); assert r2["banned"]
    print("OK  2 faux TXID refusés = bannissement")
    assert await db.refuse(b, 99) is None
    c = await db.create_order(1, pid, 1500, "virement_paypal", None, None)
    r3 = await db.refuse(c, 99); assert r3["strikes"] == 0
    print("OK  refus virement sans strike")
    await db.set_setting("lots", "X\nY\nZ\nW"); await db.track(1, "Fiche:Guide")
    await db.run("INSERT INTO wheel_spins(user_id,lot,created_at) VALUES(1,'X',?)", (db.now(),))

asyncio.run(main())

# Persistance : un nouveau processus Python = un redémarrage du bot
code = """
import asyncio, database as db
async def m():
    r = await db.one('SELECT COUNT(*) n FROM orders'); u = await db.one('SELECT banned FROM users WHERE id=2')
    l = await db.setting('lots'); print(r['n'], u['banned'], l.count(chr(10)))
asyncio.run(m())
"""
out = subprocess.run([sys.executable, "-c", code], cwd=root, env=os.environ, capture_output=True, text=True)
assert out.stdout.split() == ["4", "1", "3"], out
print("OK  données conservées après redémarrage")

# Sauvegarde puis restauration
subprocess.run([sys.executable, "backup.py"], cwd=root, env=os.environ, check=True)
bk = next(BACKUPS.glob("stych-*.db.gz")).name
c = sqlite3.connect(DB_PATH); c.execute("DELETE FROM payments"); c.execute("DELETE FROM orders"); c.commit(); c.close()
subprocess.run([sys.executable, "restore.py", bk], cwd=root, env=os.environ, check=True)
c = sqlite3.connect(DB_PATH); n = c.execute("SELECT COUNT(*) FROM orders").fetchone()[0]; c.close()
assert n == 4
print("OK  sauvegarde + restauration")
print("TOUS LES TESTS OK")
