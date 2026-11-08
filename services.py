import html
import io
import logging
import time

import aiohttp
from aiogram.types import FSInputFile, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database as db
from config import ADMIN_IDS, EBOOKS

log = logging.getLogger("stych")
h = html.escape
COINS = [("SOL", "Solana", "solana", "🟣"), ("BTC", "Bitcoin", "bitcoin", "🟠"),
         ("ETH", "Ethereum", "ethereum", "🔷"), ("USDC", "USDC (réseau Ethereum)", "usd-coin", "🔵")]
DEC = {"SOL": 4, "BTC": 8, "ETH": 6, "USDC": 2}
DEFAULT_LOTS = ["LOT A", "LOT B", "LOT C", "LOT D"]


def eur(c):
    return f"{c / 100:.2f}".replace(".00", "") + " €"


def kb(*rows):
    b = InlineKeyboardBuilder()
    for row in rows:
        b.row(*[InlineKeyboardButton(text=t, url=d) if d.startswith("http") else InlineKeyboardButton(text=t, callback_data=d) for t, d in row])
    return b.as_markup()


MENU = kb([("🛍 Boutique", "shop")], [("🎡 Roue", "wheel"), ("📦 Mes commandes", "orders")], [("🎟 Codes promo", "promo"), ("💬 Aide", "help")])


async def show(c, text, markup=None, photo=None):
    try:
        await c.message.delete()
    except Exception:
        pass
    if photo:
        await c.message.answer_photo(photo, caption=text, reply_markup=markup)
    else:
        await c.message.answer(text, reply_markup=markup)
    await c.answer()


_rates = {"t": 0, "d": None}


async def rates():
    """Cours EUR du moment (API publique CoinGecko). None si indisponible."""
    if _rates["d"] and time.time() - _rates["t"] < 60:
        return _rates["d"]
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=solana,bitcoin,ethereum,usd-coin&vs_currencies=eur"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6)) as s:
            async with s.get(url) as r:
                d = await r.json()
        if all(d.get(c[2], {}).get("eur") for c in COINS):
            _rates.update(t=time.time(), d=d)
            return d
    except Exception:
        log.warning("Cours crypto indisponible")
    return None


def qr_png(text):
    import qrcode
    b = io.BytesIO()
    qrcode.make(text).save(b, "PNG")
    return b.getvalue()


async def promo_ok(code, pid=None):
    c = await db.one("SELECT * FROM promo_codes WHERE code=? AND active=1", (code,))
    if not c or (pid and c["product_id"] and c["product_id"] != pid):
        return None
    if (c["expires_at"] and c["expires_at"] < time.time()) or (c["max_uses"] and c["used"] >= c["max_uses"]):
        return None
    return c


async def price_for(uid, p):
    """Retourne (prix_en_centimes, code_promo_appliqué_ou_None)."""
    u = await db.one("SELECT promo FROM users WHERE id=?", (uid,))
    pr = await promo_ok(u["promo"], p["id"]) if u and u["promo"] else None
    v = p["price"]
    if pr:
        v = round(v * (100 - pr["pct"]) / 100) if pr["pct"] else max(0, v - pr["fixed"])
    return v, (pr["code"] if pr else None)


async def lots():
    raw = await db.setting("lots")
    return raw.split("\n") if raw else DEFAULT_LOTS


async def deliver(bot, uid, pid):
    """Vérifie côté serveur que le client a bien acheté, puis envoie le PDF."""
    if not await db.one("SELECT 1 x FROM purchases WHERE user_id=? AND product_id=?", (uid, pid)):
        return False
    p = await db.one("SELECT name,pdf FROM products WHERE id=?", (pid,))
    path = EBOOKS / p["pdf"] if p and p["pdf"] else None
    if not path or not path.exists():
        await bot.send_message(uid, "✅ Paiement validé, mais le fichier est momentanément indisponible. Le support va te l'envoyer.")
        for a in ADMIN_IDS:
            await bot.send_message(a, f"⚠️ PDF manquant pour « {h(p['name'] if p else pid)} » (client {uid}).")
        return False
    await bot.send_document(uid, FSInputFile(path, filename=f"{p['name']}.pdf"), caption="📥 Voici ton guide. Merci pour ta confiance !", protect_content=True)
    return True


async def notify_admins(bot, oid, only=None):
    o = await db.one("SELECT o.*,u.username,u.first_name,p.name pname,pay.txid FROM orders o "
                     "JOIN users u ON u.id=o.user_id JOIN products p ON p.id=o.product_id "
                     "LEFT JOIN payments pay ON pay.order_id=o.id WHERE o.id=?", (oid,))
    who = h(o["first_name"] or "—") + (f" (@{o['username']})" if o["username"] else "")
    mode = {"virement_paypal": "Virement / PayPal", "test": "TEST (aucun vrai paiement)"}.get(o["method"], o["method"].replace("crypto:", "Crypto "))
    t = (f"<b>NOUVELLE COMMANDE À VÉRIFIER</b>\n\nCommande : <b>#{oid}</b>\nClient : {who}\nID Telegram : <code>{o['user_id']}</code>\n"
         f"Produit : {h(o['pname'])}\nMontant : {eur(o['amount'])}\nMode : {mode}\n"
         f"Date : {time.strftime('%d/%m/%Y %H:%M', time.localtime(o['created_at']))}\n")
    t += f"TXID : <code>{o['txid']}</code>\n\n⚠️ Vérifie ce TXID sur l'explorateur blockchain et la réception des fonds avant de valider." if o["txid"] else \
        "\n⚠️ Vérifie la réception réelle du paiement sur ton compte avant de valider."
    markup = kb([("✅ VALIDER LE PAIEMENT", f"ok:{oid}")], [("❌ REFUSER LE PAIEMENT", f"no:{oid}")])
    for a in ([only] if only else ADMIN_IDS):
        try:
            await bot.send_message(a, t, reply_markup=markup)
        except Exception:
            log.exception("Notification admin impossible")
