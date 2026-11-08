"""SQLite persistant. Toutes les données vivent dans DATA/stych.db (hors du code :
une mise à jour du bot ne touche jamais ce dossier)."""
import asyncio
import sqlite3
import time

from config import DB_PATH

now = lambda: int(time.time())

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
  strikes INTEGER NOT NULL DEFAULT 0, banned INTEGER NOT NULL DEFAULT 0,
  last_spin INTEGER NOT NULL DEFAULT 0, promo TEXT, marketing INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS products(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, short TEXT, perks TEXT,
  price INTEGER NOT NULL, cat TEXT, cover TEXT, cover_file TEXT, pdf TEXT,
  active INTEGER NOT NULL DEFAULT 1, deleted INTEGER NOT NULL DEFAULT 0,
  sales INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id),
  product_id INTEGER NOT NULL REFERENCES products(id), amount INTEGER NOT NULL,
  method TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
  created_at INTEGER NOT NULL, decided_by INTEGER, decided_at INTEGER, reason TEXT);
CREATE TABLE IF NOT EXISTS payments(
  id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL REFERENCES orders(id),
  method TEXT NOT NULL, txid TEXT UNIQUE, amount INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS purchases(
  user_id INTEGER NOT NULL, product_id INTEGER NOT NULL, order_id INTEGER,
  created_at INTEGER NOT NULL, PRIMARY KEY(user_id, product_id));
CREATE TABLE IF NOT EXISTS promo_codes(
  code TEXT PRIMARY KEY, pct INTEGER NOT NULL DEFAULT 0, fixed INTEGER NOT NULL DEFAULT 0,
  product_id INTEGER, expires_at INTEGER, max_uses INTEGER,
  used INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS admin_logs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT, detail TEXT, created_at INTEGER);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS wheel_spins(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, lot TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX IF NOT EXISTS ix_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS ix_orders_user ON orders(user_id);
CREATE INDEX IF NOT EXISTS ix_events_name ON events(name);
"""
# Mises à jour futures du schéma : ajouter un script ici, jamais modifier SCHEMA.
# Les données existantes sont conservées (PRAGMA user_version suit la version).
MIGRATIONS: list[str] = []


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA busy_timeout=15000")
    c.execute("PRAGMA synchronous=FULL")
    return c


def init():
    """Crée la base au premier démarrage, puis applique les migrations éventuelles."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = _conn()
    try:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        v = c.execute("PRAGMA user_version").fetchone()[0]
        for i, s in enumerate(MIGRATIONS[v:], start=v + 1):
            c.executescript(s)
            c.execute(f"PRAGMA user_version={i}")
        c.commit()
    finally:
        c.close()


def _exec(sql, args, mode):
    c = _conn()
    try:
        cur = c.execute(sql, args)
        if mode == "all":
            r = [dict(x) for x in cur.fetchall()]
        elif mode == "one":
            x = cur.fetchone()
            r = dict(x) if x else None
        else:
            r = (cur.lastrowid, cur.rowcount)
        c.commit()
        return r
    finally:
        c.close()


async def all_(sql, a=()):
    return await asyncio.to_thread(_exec, sql, a, "all")


async def one(sql, a=()):
    return await asyncio.to_thread(_exec, sql, a, "one")


async def run(sql, a=()):
    return await asyncio.to_thread(_exec, sql, a, "run")


async def setting(key, default=None):
    r = await one("SELECT value FROM settings WHERE key=?", (key,))
    return r["value"] if r else default


async def set_setting(key, value):
    await run("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


async def track(uid, name):
    await run("INSERT INTO events(user_id,name,created_at) VALUES(?,?,?)", (uid, name, now()))


async def upsert_user(u):
    await run("INSERT INTO users(id,username,first_name,created_at) VALUES(?,?,?,?) "
              "ON CONFLICT(id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name",
              (u.id, u.username, u.first_name, now()))


async def log_admin(admin_id, action, detail=""):
    await run("INSERT INTO admin_logs(admin_id,action,detail,created_at) VALUES(?,?,?,?)", (admin_id, action, detail, now()))


def _create_order(uid, pid, amount, method, txid, promo):
    c = _conn()
    try:
        oid = c.execute("INSERT INTO orders(user_id,product_id,amount,method,status,created_at) VALUES(?,?,?,?,'pending',?)",
                        (uid, pid, amount, method, now())).lastrowid
        # txid UNIQUE : un TXID déjà utilisé lève sqlite3.IntegrityError et tout est annulé
        c.execute("INSERT INTO payments(order_id,method,txid,amount,status,created_at) VALUES(?,?,?,?,'pending',?)",
                  (oid, method, txid, amount, now()))
        if promo:
            c.execute("UPDATE promo_codes SET used=used+1 WHERE code=?", (promo,))
        c.commit()
        return oid
    finally:
        c.close()


async def create_order(uid, pid, amount, method, txid, promo):
    return await asyncio.to_thread(_create_order, uid, pid, amount, method, txid, promo)


def _validate(oid, admin):
    c = _conn()
    try:
        # UPDATE conditionnel = une seule validation possible, jamais de double livraison
        if c.execute("UPDATE orders SET status='paid',decided_by=?,decided_at=? WHERE id=? AND status='pending'",
                     (admin, now(), oid)).rowcount == 0:
            return None
        o = c.execute("SELECT user_id,product_id FROM orders WHERE id=?", (oid,)).fetchone()
        if c.execute("INSERT OR IGNORE INTO purchases(user_id,product_id,order_id,created_at) VALUES(?,?,?,?)",
                     (o["user_id"], o["product_id"], oid, now())).rowcount:
            c.execute("UPDATE products SET sales=sales+1 WHERE id=?", (o["product_id"],))
        c.execute("UPDATE payments SET status='confirmed' WHERE order_id=?", (oid,))
        c.execute("INSERT INTO admin_logs(admin_id,action,detail,created_at) VALUES(?,?,?,?)", (admin, "validate", f"order {oid}", now()))
        c.commit()
        return dict(o)
    finally:
        c.close()


def _refuse(oid, admin):
    c = _conn()
    try:
        if c.execute("UPDATE orders SET status='refused',decided_by=?,decided_at=? WHERE id=? AND status='pending'",
                     (admin, now(), oid)).rowcount == 0:
            return None
        o = c.execute("SELECT user_id,method FROM orders WHERE id=?", (oid,)).fetchone()
        c.execute("UPDATE payments SET status='refused' WHERE order_id=?", (oid,))
        crypto = o["method"].startswith("crypto")
        if crypto:  # faux TXID : 2 refus = bannissement automatique
            c.execute("UPDATE users SET strikes=strikes+1 WHERE id=?", (o["user_id"],))
            c.execute("UPDATE users SET banned=1 WHERE id=? AND strikes>=2", (o["user_id"],))
        u = c.execute("SELECT strikes,banned FROM users WHERE id=?", (o["user_id"],)).fetchone()
        c.execute("INSERT INTO admin_logs(admin_id,action,detail,created_at) VALUES(?,?,?,?)", (admin, "refuse", f"order {oid}", now()))
        c.commit()
        return {"user_id": o["user_id"], "strikes": u["strikes"], "banned": u["banned"], "crypto": crypto}
    finally:
        c.close()


async def validate(oid, admin):
    return await asyncio.to_thread(_validate, oid, admin)


async def refuse(oid, admin):
    return await asyncio.to_thread(_refuse, oid, admin)
