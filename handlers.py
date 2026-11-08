"""Parcours client : boutique, paiement crypto / virement, commandes, roue, promos."""
import html
import logging
import random
import re
import secrets
import sqlite3
import asyncio
import time
from urllib.parse import quote

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

import database as db
import services as sv
from config import ADMIN_IDS, ADMIN_USERNAME, STORE, SUPPORT
from services import COINS, DEC, MENU, eur, h, kb, show

r = Router()
log = logging.getLogger("stych")


class St(StatesGroup):
    txid = State()
    promo = State()


BACK = [("‹ Menu", "menu")]


@r.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    await db.run("UPDATE users SET marketing=1 WHERE id=? AND created_at>=?", (m.from_user.id, int(time.time()) - 5))
    await db.track(m.from_user.id, "Ouverture du bot")
    await m.answer(f"<b>{h(STORE)}</b>\nDes guides concrets, livrés en PDF dès que ton paiement est vérifié.", reply_markup=MENU)


@r.callback_query(F.data == "menu")
async def menu(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await show(c, f"<b>{h(STORE)}</b>\nQue veux-tu faire ?", MENU)


@r.message(Command("stop"))
async def stop(m: Message):
    await db.run("UPDATE users SET marketing=0 WHERE id=?", (m.from_user.id,))
    await m.answer("Tu ne recevras plus de messages promotionnels. /resume pour les réactiver.")


@r.message(Command("resume"))
async def resume(m: Message):
    await db.run("UPDATE users SET marketing=1 WHERE id=?", (m.from_user.id,))
    await m.answer("Messages promotionnels réactivés.")


@r.callback_query(F.data == "shop")
async def shop(c: CallbackQuery):
    await db.track(c.from_user.id, "Onglet:shop")
    ps = await db.all_("SELECT id,name,price FROM products WHERE active=1 AND deleted=0 ORDER BY sales DESC,id DESC")
    if not ps:
        return await show(c, "📚 Le catalogue arrive bientôt.", kb(BACK))
    await show(c, "<b>La boutique</b>\nChoisis un guide.", kb(*[[(f"{p['name']} · {eur(p['price'])}", f"p:{p['id']}")] for p in ps], BACK))


@r.callback_query(F.data.startswith("p:"))
async def product(c: CallbackQuery):
    pid = int(c.data[2:])
    p = await db.one("SELECT * FROM products WHERE id=? AND active=1 AND deleted=0", (pid,))
    if not p:
        return await c.answer("Ce guide n'est plus disponible.", show_alert=True)
    await db.track(c.from_user.id, "Fiche:" + p["name"])
    owned = await db.one("SELECT 1 x FROM purchases WHERE user_id=? AND product_id=?", (c.from_user.id, pid))
    price, _ = await sv.price_for(c.from_user.id, p)
    perks = "\n".join("✓ " + h(x) for x in (p["perks"] or "").split("\n") if x.strip())
    text = f"<b>{h(p['name'])}</b>\n{h(p['short'] or '')}\n\n{perks}\n\n{p['sales']} lecteurs · <b>{eur(price)}</b>"
    btn = [("📥 Renvoyer mon PDF", f"dl:{pid}")] if owned else [(f"Débloquer · {eur(price)}", f"buy:{pid}")]
    await show(c, text, kb(btn, [("‹ Boutique", "shop")]), photo=p["cover"])


async def _product(pid):
    return await db.one("SELECT * FROM products WHERE id=? AND active=1 AND deleted=0", (pid,))


@r.callback_query(F.data.startswith("buy:"))
async def buy(c: CallbackQuery):
    pid = int(c.data[4:])
    p = await _product(pid)
    if not p:
        return await c.answer("Indisponible", show_alert=True)
    if await db.one("SELECT 1 x FROM purchases WHERE user_id=? AND product_id=?", (c.from_user.id, pid)):
        return await c.answer("Tu possèdes déjà ce guide.", show_alert=True)
    await db.track(c.from_user.id, "Achat lancé")
    price, _ = await sv.price_for(c.from_user.id, p)
    coins = [(f"{e} {n.split(' (')[0]}", f"coin:{pid}:{i}") for i, (_, n, _, e) in enumerate(COINS)]
    await show(c, f"<b>Comment veux-tu payer ?</b>\n{h(p['name'])} · <b>{eur(price)}</b>",
               kb(coins[:2], coins[2:], [("💬 Virement ou PayPal", f"chat:{pid}")], [("‹ Retour", f"p:{pid}")]))


@r.callback_query(F.data.startswith("coin:"))
async def coin(c: CallbackQuery):
    _, pid, i = c.data.split(":")
    pid, i = int(pid), int(i)
    sym, name, cg, _ = COINS[i]
    p = await _product(pid)
    addr = await db.setting("addr_" + sym)
    if not p:
        return await c.answer("Indisponible", show_alert=True)
    if not addr:
        return await c.answer("Ce moyen de paiement n'est pas encore configuré.", show_alert=True)
    await db.track(c.from_user.id, "Paiement:" + sym)
    price, _ = await sv.price_for(c.from_user.id, p)
    rt = await sv.rates()
    line = (f"Envoie exactement <b>{price / 100 / rt[cg]['eur']:.{DEC[sym]}f} {sym}</b> (≈ {eur(price)}, cours du moment)"
            if rt else f"Envoie la somme exacte : <b>{eur(price)}</b>")
    cap = f"<b>{name}</b>\n{line}\n\nAdresse :\n<code>{h(addr)}</code>\n\nPuis clique sur « J'ai payé »."
    try:
        await c.message.delete()
    except Exception:
        pass
    await c.message.answer_photo(BufferedInputFile(sv.qr_png(addr), "qr.png"), caption=cap,
                                 reply_markup=kb([("✅ J'ai payé", f"paid:{pid}:{i}")], [("‹ Retour", f"buy:{pid}")]))
    await c.answer()


@r.callback_query(F.data.startswith("paid:"))
async def paid(c: CallbackQuery, state: FSMContext):
    _, pid, i = c.data.split(":")
    await state.set_state(St.txid)
    await state.update_data(pid=int(pid), i=int(i))
    await show(c, "Colle ici le <b>TXID</b> de ta transaction.\nL'administrateur le vérifie sur la blockchain avant de livrer ton guide.", kb(BACK))


@r.message(St.txid, F.text)
async def txid(m: Message, state: FSMContext):
    tx = m.text.strip()
    if not re.fullmatch(r"(0x)?[A-Za-z0-9]{20,100}", tx):
        return await m.answer("TXID invalide. Copie l'identifiant complet de la transaction.")
    d = await state.get_data()
    p = await _product(d["pid"])
    if not p:
        return await m.answer("Ce guide n'est plus disponible.")
    if (await db.one("SELECT COUNT(*) n FROM orders WHERE user_id=? AND status='pending'", (m.from_user.id,)))["n"] >= 3:
        return await m.answer("Tu as déjà 3 paiements en cours de vérification. Patiente un peu.")
    price, promo = await sv.price_for(m.from_user.id, p)
    try:
        oid = await db.create_order(m.from_user.id, p["id"], price, "crypto:" + COINS[d["i"]][0], tx, promo)
    except sqlite3.IntegrityError:
        return await m.answer("Ce TXID a déjà été utilisé.")
    await state.clear()
    await db.track(m.from_user.id, "TXID envoyé")
    await sv.notify_admins(m.bot, oid)
    await m.answer(f"⏳ <b>Paiement en vérification</b>\nCommande #{oid}. Tu seras notifié dès la validation.", reply_markup=MENU)


@r.callback_query(F.data.startswith("chat:"))
async def chat(c: CallbackQuery):
    p = await _product(int(c.data[5:]))
    if not p:
        return await c.answer("Indisponible", show_alert=True)
    if not ADMIN_USERNAME:
        return await c.answer("Contact admin non configuré.", show_alert=True)
    price, promo = await sv.price_for(c.from_user.id, p)
    oid = await db.create_order(c.from_user.id, p["id"], price, "virement_paypal", None, promo)
    await db.track(c.from_user.id, "Paiement:Virement / PayPal")
    await sv.notify_admins(c.bot, oid)
    msg = quote(f"Bonjour, commande #{oid} : {p['name']} ({eur(price)}). Je souhaite payer par virement ou PayPal.")
    await show(c, f"💬 Commande <b>#{oid}</b> créée.\nOuvre le chat pour recevoir les instructions de paiement.",
               kb([("Ouvrir le chat Telegram", f"https://t.me/{ADMIN_USERNAME}?text={msg}")], [("📦 Mes commandes", "orders")]))


STATUS = {"pending": "⏳ En vérification", "paid": "✅ Livrée", "refused": "❌ Refusée", "refunded": "↩️ Remboursée"}


@r.callback_query(F.data == "orders")
async def orders(c: CallbackQuery):
    await db.track(c.from_user.id, "Onglet:orders")
    os_ = await db.all_("SELECT o.id,o.status,o.amount,p.name,o.product_id FROM orders o JOIN products p ON p.id=o.product_id "
                        "WHERE o.user_id=? AND o.method!='test' ORDER BY o.id DESC LIMIT 15", (c.from_user.id,))
    if not os_:
        return await show(c, "🛍 <b>Tu n'as pas encore acheté de guide</b>\nTes achats apparaîtront ici.", kb([("Découvrir la boutique", "shop")], BACK))
    txt = "<b>Mes commandes</b>\n\n" + "\n".join(f"#{o['id']} · {h(o['name'])} · {eur(o['amount'])} · {STATUS[o['status']]}" for o in os_)
    dl = [[(f"📥 {o['name'][:28]}", f"dl:{o['product_id']}")] for o in os_ if o["status"] == "paid"]
    await show(c, txt, kb(*dl, BACK))


@r.callback_query(F.data.startswith("dl:"))
async def dl(c: CallbackQuery):
    ok = await sv.deliver(c.bot, c.from_user.id, int(c.data[3:]))  # droits vérifiés en base
    await c.answer("PDF envoyé ✅" if ok else "Tu n'as pas accès à ce guide.", show_alert=not ok)


@r.callback_query(F.data == "wheel")
async def wheel(c: CallbackQuery):
    await db.track(c.from_user.id, "Onglet:wheel")
    lots = await sv.lots()
    u = await db.one("SELECT last_spin FROM users WHERE id=?", (c.from_user.id,))
    left = u["last_spin"] + 86400 - time.time()
    t = "<b>🎡 La roue</b>\nUn tour toutes les 24 h.\n\n" + " · ".join(lots)
    if left > 0:
        return await show(c, t + f"\n\nProchain tour dans {int(left // 3600)} h {int(left % 3600 // 60):02d} min", kb(BACK))
    await show(c, t, kb([("🎡 Tourner la roue", "spin")], BACK))


@r.callback_query(F.data == "spin")
async def spin(c: CallbackQuery):
    n = int(time.time())
    # réservation atomique : impossible de tourner deux fois dans les 24 h
    _, rc = await db.run("UPDATE users SET last_spin=? WHERE id=? AND last_spin<=?", (n, c.from_user.id, n - 86400))
    if not rc:
        return await c.answer("Tu as déjà tourné aujourd'hui.", show_alert=True)
    lot = secrets.choice(await sv.lots())
    await db.run("INSERT INTO wheel_spins(user_id,lot,created_at) VALUES(?,?,?)", (c.from_user.id, lot, n))
    await db.track(c.from_user.id, "Roue tournée")
    await c.message.edit_text("🎡 La roue tourne…")
    await asyncio.sleep(1.5)
    await c.message.edit_text(f"🎉 Tu as gagné : <b>{h(lot)}</b>\nL'administrateur te contactera pour te le remettre.", reply_markup=kb(BACK))
    for a in ADMIN_IDS:
        try:
            await c.bot.send_message(a, f"🎡 {h(c.from_user.first_name or '')} (<code>{c.from_user.id}</code>) a gagné : <b>{h(lot)}</b>")
        except Exception:
            pass
    await c.answer()


@r.callback_query(F.data == "promo")
async def promo(c: CallbackQuery, state: FSMContext):
    await state.set_state(St.promo)
    await show(c, "Envoie ton code promo.", kb(BACK))


@r.message(St.promo, F.text)
async def promo_in(m: Message, state: FSMContext):
    code = m.text.strip().upper()
    if not await sv.promo_ok(code):
        return await m.answer("Code invalide, expiré ou épuisé. Réessaie ou /start.")
    await db.run("UPDATE users SET promo=? WHERE id=?", (code, m.from_user.id))
    await state.clear()
    await m.answer(f"✅ Code <b>{h(code)}</b> activé : il s'applique à ta prochaine commande.", reply_markup=MENU)


@r.callback_query(F.data == "help")
async def help_(c: CallbackQuery):
    await db.track(c.from_user.id, "Onglet:help")
    rows = [[("💬 Contacter le support", f"https://t.me/{SUPPORT}")]] if SUPPORT else []
    await show(c, f"<b>Aide</b>\n{h(STORE)} : des eBooks clairs et utiles, livrés en PDF dès que ton paiement est vérifié.", kb(*rows, BACK))


@r.message(Command("admin", "stats", "orders", "products", "broadcast", "test", "promo"))
async def denied(m: Message):
    await db.log_admin(m.from_user.id, "acces_refuse", (m.text or "")[:80])
    log.warning("Tentative d'accès admin refusée : %s", m.from_user.id)
    await m.answer("Commande inconnue.")
