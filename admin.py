"""Espace administrateur. Tout est réservé aux ADMIN_ID, vérifié côté serveur."""
import asyncio
import logging
import time
import uuid

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import database as db
import services as sv
from config import ADMIN_IDS, COVERS, EBOOKS, SUPPORT
from services import COINS, eur, h, kb

r = Router()
r.message.filter(F.from_user.id.in_(ADMIN_IDS))
r.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))
log = logging.getLogger("stych")
PANEL = kb([("🛒 Commandes à vérifier", "ao")], [("📚 Produits", "ap"), ("➕ Ajouter un eBook", "anew")],
           [("💰 Paiement", "apay"), ("🎡 Roue", "aw")], [("📊 Statistiques", "ast"), ("👤 Clients bannis", "au")])
TEXT_FIELDS = {"name": "le titre", "short": "la description courte", "perks": "le contenu (un avantage par ligne)", "price": "le prix en €", "cat": "la catégorie"}


class A(StatesGroup):
    name = State(); price = State(); cat = State(); short = State(); perks = State(); cover = State(); pdf = State()
    edit = State(); ecover = State(); epdf = State(); addr = State(); lots = State()


def cents(t):
    try:
        v = round(float(t.replace(",", ".").replace("€", "").strip()) * 100)
        return v if v > 0 else None
    except ValueError:
        return None


async def save_pdf(bot, doc):
    if not (doc.mime_type == "application/pdf" or (doc.file_name or "").lower().endswith(".pdf")):
        raise ValueError("Envoie un fichier PDF.")
    if doc.file_size and doc.file_size > 20 * 1024 * 1024:
        raise ValueError("PDF trop lourd : 20 Mo maximum (limite Telegram).")
    EBOOKS.mkdir(parents=True, exist_ok=True)
    name = uuid.uuid4().hex + ".pdf"
    await bot.download(doc, destination=EBOOKS / name)
    return name


async def save_cover(bot, photo):
    COVERS.mkdir(parents=True, exist_ok=True)
    name = uuid.uuid4().hex + ".jpg"
    await bot.download(photo, destination=COVERS / name)
    return photo.file_id, name


async def card(target, p, markup):
    perks = "\n".join("✓ " + h(x) for x in (p["perks"] or "").split("\n") if x.strip())
    t = f"<b>{h(p['name'])}</b>\n{h(p['short'] or '')}\n\n{perks}\n\n<b>{eur(p['price'])}</b>"
    if p["cover"]:
        await target.answer_photo(p["cover"], caption=t, reply_markup=markup)
    else:
        await target.answer(t, reply_markup=markup)


@r.message(Command("admin"))
async def admin(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("<b>Administration</b>", reply_markup=PANEL)


@r.callback_query(F.data == "adm")
async def adm(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await sv.show(c, "<b>Administration</b>", PANEL)


async def pending(msg):
    os_ = await db.all_("SELECT id FROM orders WHERE status='pending' ORDER BY id LIMIT 20")
    if not os_:
        return await msg.answer("✅ Aucune commande en attente.", reply_markup=PANEL)
    for o in os_:
        await sv.notify_admins(msg.bot, o["id"], only=msg.chat.id)


@r.message(Command("orders"))
async def orders_cmd(m: Message):
    await pending(m)


@r.callback_query(F.data == "ao")
async def orders_cb(c: CallbackQuery):
    await c.answer()
    await pending(c.message)


@r.callback_query(F.data.startswith("ok:"))
async def ok(c: CallbackQuery):
    oid = int(c.data[3:])
    o = await db.validate(oid, c.from_user.id)
    if not o:
        return await c.answer("Commande déjà traitée.", show_alert=True)
    await db.track(o["user_id"], "Commande validée")
    try:
        await c.message.edit_text(c.message.html_text + f"\n\n✅ <b>VALIDÉE</b> par {c.from_user.id}")
    except Exception:
        pass
    await c.bot.send_message(o["user_id"], f"✅ <b>Paiement confirmé</b> (commande #{oid}). Ton guide arrive.")
    await sv.deliver(c.bot, o["user_id"], o["product_id"])
    await c.answer("Validée et livrée")


@r.callback_query(F.data.startswith("no:"))
async def no(c: CallbackQuery):
    oid = int(c.data[3:])
    res = await db.refuse(oid, c.from_user.id)
    if not res:
        return await c.answer("Commande déjà traitée.", show_alert=True)
    await db.track(res["user_id"], "Commande refusée")
    try:
        await c.message.edit_text(c.message.html_text + f"\n\n❌ <b>REFUSÉE</b> par {c.from_user.id}" + ("\n🚫 Client banni automatiquement." if res["banned"] else ""))
    except Exception:
        pass
    if res["banned"]:
        who = f"@{SUPPORT}" if SUPPORT else "l'administrateur"
        txt = f"🚫 Ton accès est suspendu après plusieurs paiements refusés. Contacte-moi sur Telegram : {who}"
    else:
        txt = f"❌ Ton paiement (commande #{oid}) n'a pas pu être confirmé."
        if res["crypto"]:
            txt += "\n⚠️ Attention : un second refus suspendra ton accès."
    try:
        await c.bot.send_message(res["user_id"], txt)
    except Exception:
        pass
    await c.answer("Refusée")


@r.message(Command("test"))
async def test(m: Message):
    p = await db.one("SELECT id FROM products WHERE deleted=0 ORDER BY id LIMIT 1")
    if not p:
        return await m.answer("Ajoute d'abord un eBook.")
    await db.upsert_user(m.from_user)
    oid = await db.create_order(m.from_user.id, p["id"], 0, "test", None, None)
    await sv.notify_admins(m.bot, oid, only=m.chat.id)


@r.message(Command("products"))
async def products_cmd(m: Message):
    await products(m)


@r.callback_query(F.data == "ap")
async def products_cb(c: CallbackQuery):
    await c.answer()
    await products(c.message)


async def products(msg):
    ps = await db.all_("SELECT * FROM products WHERE deleted=0 ORDER BY id")
    if not ps:
        return await msg.answer("Aucun eBook. Utilise ➕ Ajouter un eBook.", reply_markup=PANEL)
    for p in ps:
        await msg.answer(f"<b>{h(p['name'])}</b> · {eur(p['price'])}\n{p['sales']} ventes · {'actif' if p['active'] else 'désactivé'} · "
                         f"{'PDF ✓' if p['pdf'] else 'sans PDF'} · {'image ✓' if p['cover'] else 'sans image'}",
                         reply_markup=kb([("✏️ Modifier", f"e:{p['id']}"), ("🔁 Activer/Désactiver", f"tg:{p['id']}")], [("🗑 Supprimer", f"del:{p['id']}")]))


@r.callback_query(F.data.startswith("tg:"))
async def toggle(c: CallbackQuery):
    await db.run("UPDATE products SET active=1-active WHERE id=?", (int(c.data[3:]),))
    await db.log_admin(c.from_user.id, "toggle", c.data)
    await c.answer("Boutique mise à jour ✅")


@r.callback_query(F.data.startswith("del:"))
async def delete(c: CallbackQuery):
    pid = c.data[4:]
    await c.message.edit_text("Supprimer ce produit de la boutique ? Les clients qui l'ont acheté gardent leur accès.",
                              reply_markup=kb([("Oui, supprimer", f"delok:{pid}")], [("Annuler", "adm")]))
    await c.answer()


@r.callback_query(F.data.startswith("delok:"))
async def delok(c: CallbackQuery):
    await db.run("UPDATE products SET deleted=1,active=0 WHERE id=?", (int(c.data[6:]),))
    await db.log_admin(c.from_user.id, "delete", c.data)
    await c.message.edit_text("🗑 Produit supprimé.")
    await c.answer()


@r.callback_query(F.data.startswith("e:"))
async def edit_menu(c: CallbackQuery):
    pid = c.data[2:]
    await sv.show(c, "Que veux-tu modifier ?", kb([("Titre", f"ef:{pid}:name"), ("Description", f"ef:{pid}:short")],
                  [("Contenu", f"ef:{pid}:perks"), ("Prix", f"ef:{pid}:price")], [("Catégorie", f"ef:{pid}:cat")],
                  [("🖼 Couverture", f"ec:{pid}"), ("📄 PDF", f"ep:{pid}")], [("‹ Admin", "adm")]))


@r.callback_query(F.data.startswith("ef:"))
async def edit_field(c: CallbackQuery, state: FSMContext):
    _, pid, f = c.data.split(":")
    await state.set_state(A.edit)
    await state.update_data(pid=int(pid), f=f)
    await sv.show(c, f"Envoie {TEXT_FIELDS[f]}.", kb([("Annuler", "adm")]))


@r.message(A.edit, F.text)
async def edit_val(m: Message, state: FSMContext):
    d = await state.get_data()
    v = cents(m.text) if d["f"] == "price" else m.text.strip()
    if v is None:
        return await m.answer("Prix invalide. Exemple : 15 ou 12,50")
    await db.run(f"UPDATE products SET {d['f']}=? WHERE id=?", (v, d["pid"]))  # champ issu d'une liste fermée
    await db.log_admin(m.from_user.id, "edit", f"{d['pid']}:{d['f']}")
    await state.clear()
    await m.answer("✅ Modifié. Visible tout de suite dans la boutique.", reply_markup=PANEL)


@r.callback_query(F.data.startswith("ec:"))
async def edit_cover(c: CallbackQuery, state: FSMContext):
    await state.set_state(A.ecover)
    await state.update_data(pid=int(c.data[3:]))
    await sv.show(c, "Envoie la nouvelle photo de couverture.", kb([("Annuler", "adm")]))


@r.message(A.ecover, F.photo)
async def edit_cover_in(m: Message, state: FSMContext):
    d = await state.get_data()
    fid, name = await save_cover(m.bot, m.photo[-1])
    await db.run("UPDATE products SET cover=?,cover_file=? WHERE id=?", (fid, name, d["pid"]))
    await state.clear()
    await m.answer("✅ Couverture changée.", reply_markup=PANEL)


@r.callback_query(F.data.startswith("ep:"))
async def edit_pdf(c: CallbackQuery, state: FSMContext):
    await state.set_state(A.epdf)
    await state.update_data(pid=int(c.data[3:]))
    await sv.show(c, "Envoie le nouveau fichier PDF.", kb([("Annuler", "adm")]))


@r.message(A.epdf, F.document)
async def edit_pdf_in(m: Message, state: FSMContext):
    try:
        name = await save_pdf(m.bot, m.document)
    except ValueError as e:
        return await m.answer(str(e))
    d = await state.get_data()
    await db.run("UPDATE products SET pdf=? WHERE id=?", (name, d["pid"]))
    await db.log_admin(m.from_user.id, "pdf", str(d["pid"]))
    await state.clear()
    await m.answer("✅ PDF remplacé (l'ancien fichier reste archivé sur le serveur).", reply_markup=PANEL)


@r.callback_query(F.data == "anew")
async def add_start(c: CallbackQuery, state: FSMContext):
    await state.set_state(A.name)
    await sv.show(c, "Nouvel eBook. Quel est son <b>titre</b> ?", kb([("Annuler", "adm")]))


async def step(m, state, key, val, nxt, prompt):
    await state.update_data(**{key: val})
    await state.set_state(nxt)
    await m.answer(prompt)


@r.message(A.name, F.text)
async def a_name(m: Message, state: FSMContext):
    await step(m, state, "name", m.text.strip()[:80], A.price, "Prix en € ? (ex : 15)")


@r.message(A.price, F.text)
async def a_price(m: Message, state: FSMContext):
    c = cents(m.text)
    if c is None:
        return await m.answer("Prix invalide. Exemple : 15 ou 12,50")
    await step(m, state, "price", c, A.cat, "Catégorie ?")


@r.message(A.cat, F.text)
async def a_cat(m: Message, state: FSMContext):
    await step(m, state, "cat", m.text.strip()[:40], A.short, "Description courte (une phrase) ?")


@r.message(A.short, F.text)
async def a_short(m: Message, state: FSMContext):
    await step(m, state, "short", m.text.strip()[:200], A.perks, "Contenu et avantages : un par ligne.")


@r.message(A.perks, F.text)
async def a_perks(m: Message, state: FSMContext):
    await step(m, state, "perks", m.text.strip()[:600], A.cover, "Envoie la photo de couverture.")


@r.message(A.cover, F.photo)
async def a_cover(m: Message, state: FSMContext):
    fid, name = await save_cover(m.bot, m.photo[-1])
    await state.update_data(cover=fid, cover_file=name)
    await state.set_state(A.pdf)
    await m.answer("Envoie maintenant le fichier PDF.")


@r.message(A.pdf, F.document)
async def a_pdf(m: Message, state: FSMContext):
    try:
        name = await save_pdf(m.bot, m.document)
    except ValueError as e:
        return await m.answer(str(e))
    d = await state.get_data()
    pid, _ = await db.run("INSERT INTO products(name,short,perks,price,cat,cover,cover_file,pdf,active,created_at) VALUES(?,?,?,?,?,?,?,?,0,?)",
                          (d["name"], d["short"], d["perks"], d["price"], d["cat"], d["cover"], d["cover_file"], name, db.now()))
    await db.log_admin(m.from_user.id, "add_product", str(pid))
    await state.clear()
    p = await db.one("SELECT * FROM products WHERE id=?", (pid,))
    await m.answer("👀 <b>Prévisualisation</b> : voici la fiche telle que les clients la verront.")
    await card(m, p, kb([("✅ Publier", f"pub:{pid}")], [("🗑 Supprimer", f"delok:{pid}")]))


@r.callback_query(F.data.startswith("pub:"))
async def publish(c: CallbackQuery):
    await db.run("UPDATE products SET active=1 WHERE id=?", (int(c.data[4:]),))
    await c.answer("Publié ✅", show_alert=True)


@r.callback_query(F.data == "apay")
async def pay_menu(c: CallbackQuery):
    rows, txt = [], "<b>Adresses de paiement</b>\n"
    for sym, name, _, _ in COINS:
        a = await db.setting("addr_" + sym)
        txt += f"\n{name} : <code>{h(a)}</code>" if a else f"\n{name} : non configurée"
        rows.append([(f"✏️ {sym}", f"sa:{sym}")])
    await sv.show(c, txt, kb(*rows, [("‹ Admin", "adm")]))


@r.callback_query(F.data.startswith("sa:"))
async def pay_set(c: CallbackQuery, state: FSMContext):
    await state.set_state(A.addr)
    await state.update_data(sym=c.data[3:])
    await sv.show(c, f"Envoie ton adresse {c.data[3:]} (copie-la depuis ton portefeuille, vérifie-la bien).", kb([("Annuler", "adm")]))


@r.message(A.addr, F.text)
async def pay_in(m: Message, state: FSMContext):
    a = m.text.strip()
    if not 20 <= len(a) <= 120 or " " in a:
        return await m.answer("Adresse invalide.")
    d = await state.get_data()
    await db.set_setting("addr_" + d["sym"], a)
    await db.log_admin(m.from_user.id, "set_address", d["sym"])
    await state.clear()
    await m.answer(f"✅ Adresse {d['sym']} enregistrée :\n<code>{h(a)}</code>", reply_markup=PANEL)


@r.callback_query(F.data == "aw")
async def wheel_menu(c: CallbackQuery):
    wins = await db.all_("SELECT w.lot,w.created_at,u.first_name,u.id FROM wheel_spins w JOIN users u ON u.id=w.user_id ORDER BY w.id DESC LIMIT 10")
    t = "<b>Roue</b>\nLots : " + " · ".join(await sv.lots()) + "\n\n<b>Derniers gains</b>\n"
    t += "\n".join(f"{time.strftime('%d/%m %H:%M', time.localtime(w['created_at']))} · {h(w['first_name'] or '')} ({w['id']}) : {h(w['lot'])}" for w in wins) or "Aucun."
    await sv.show(c, t, kb([("✏️ Modifier les 4 lots", "swl")], [("‹ Admin", "adm")]))


@r.callback_query(F.data == "swl")
async def lots_set(c: CallbackQuery, state: FSMContext):
    await state.set_state(A.lots)
    await sv.show(c, "Envoie les 4 lots, un par ligne.", kb([("Annuler", "adm")]))


@r.message(A.lots, F.text)
async def lots_in(m: Message, state: FSMContext):
    ls = [x.strip()[:40] for x in m.text.split("\n") if x.strip()]
    if len(ls) != 4:
        return await m.answer("Il faut exactement 4 lignes.")
    await db.set_setting("lots", "\n".join(ls))
    await state.clear()
    await m.answer("✅ Lots enregistrés.", reply_markup=PANEL)


async def stats_text():
    q = db.one
    ca = await q("SELECT COALESCE(SUM(amount),0) v, COUNT(*) n FROM orders WHERE status='paid' AND method!='test'")
    p7 = await q("SELECT COALESCE(SUM(amount),0) v FROM orders WHERE status='paid' AND method!='test' AND decided_at>?", (int(time.time()) - 7 * 86400,))
    p30 = await q("SELECT COALESCE(SUM(amount),0) v FROM orders WHERE status='paid' AND method!='test' AND decided_at>?", (int(time.time()) - 30 * 86400,))
    cnt = {s: (await q("SELECT COUNT(*) n FROM orders WHERE status=?", (s,)))["n"] for s in ("pending", "refused")}
    users = (await q("SELECT COUNT(*) n FROM users"))["n"]
    top = await db.all_("SELECT name,sales FROM products WHERE deleted=0 ORDER BY sales DESC LIMIT 5")
    ev = {e["name"]: (e["n"], e["u"]) for e in await db.all_("SELECT name,COUNT(*) n,COUNT(DISTINCT user_id) u FROM events GROUP BY name")}
    g = lambda k: ev.get(k, (0, 0))
    t = (f"<b>📊 Statistiques</b>\n\nChiffre d'affaires : <b>{eur(ca['v'])}</b> (7 j : {eur(p7['v'])} · 30 j : {eur(p30['v'])})\n"
         f"Ventes : {ca['n']} · En attente : {cnt['pending']} · Refusées : {cnt['refused']}\nClients : {users}\n\n<b>Parcours</b> (actions / clients)\n")
    for k in ("Ouverture du bot", "Achat lancé", "TXID envoyé", "Commande validée", "Roue tournée"):
        t += f"{k} : {g(k)[0]} / {g(k)[1]}\n"
    t += "\n<b>Paiement choisi</b>\n" + ("\n".join(f"{k[9:]} : {v[0]}" for k, v in ev.items() if k.startswith("Paiement:")) or "—")
    t += "\n\n<b>Fiches les plus vues</b>\n" + ("\n".join(f"{h(k[6:])} : {v[0]}" for k, v in sorted(ev.items(), key=lambda x: -x[1][0]) if k.startswith("Fiche:"))[:800] or "—")
    t += "\n\n<b>Meilleures ventes</b>\n" + ("\n".join(f"{h(x['name'])} : {x['sales']}" for x in top) or "—")
    return t


@r.message(Command("stats"))
async def stats_cmd(m: Message):
    await m.answer(await stats_text(), reply_markup=PANEL)


@r.callback_query(F.data == "ast")
async def stats_cb(c: CallbackQuery):
    await sv.show(c, await stats_text(), kb([("‹ Admin", "adm")]))


@r.callback_query(F.data == "au")
async def banned(c: CallbackQuery):
    us = await db.all_("SELECT id,first_name,username FROM users WHERE banned=1")
    await sv.show(c, "<b>Clients bannis</b>" + ("" if us else "\nAucun."),
                  kb(*[[(f"Débannir {u['first_name'] or ''} ({u['id']})", f"unb:{u['id']}")] for u in us], [("‹ Admin", "adm")]))


@r.callback_query(F.data.startswith("unb:"))
async def unban(c: CallbackQuery):
    await db.run("UPDATE users SET banned=0,strikes=0 WHERE id=?", (int(c.data[4:]),))
    await db.log_admin(c.from_user.id, "unban", c.data)
    await c.answer("Client débanni ✅", show_alert=True)


@r.message(Command("promo"))
async def promo_cmd(m: Message):
    a = (m.text or "").split()[1:]
    if len(a) < 2 or not (a[1].endswith("%") or a[1].endswith("€")):
        return await m.answer("Usage : /promo CODE 10%  ou  /promo CODE 5€  [utilisations max]")
    try:
        n = float(a[1][:-1].replace(",", "."))
        mx = int(a[2]) if len(a) > 2 else None
    except ValueError:
        return await m.answer("Valeur invalide.")
    pct, fixed = (int(n), 0) if a[1].endswith("%") else (0, round(n * 100))
    await db.run("INSERT INTO promo_codes(code,pct,fixed,max_uses) VALUES(?,?,?,?) ON CONFLICT(code) DO UPDATE SET pct=excluded.pct,fixed=excluded.fixed,max_uses=excluded.max_uses,active=1",
                 (a[0].upper(), pct, fixed, mx))
    await m.answer(f"✅ Code {h(a[0].upper())} créé.")


@r.message(Command("broadcast"))
async def broadcast(m: Message):
    t = (m.text or "").partition(" ")[2].strip()
    if not t:
        return await m.answer("Usage : /broadcast ton message")
    us = await db.all_("SELECT id FROM users WHERE marketing=1 AND banned=0")
    n = 0
    for u in us:
        try:
            await m.bot.send_message(u["id"], h(t) + "\n\n<i>Pour ne plus recevoir nos offres : /stop</i>")
            n += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)
    await db.log_admin(m.from_user.id, "broadcast", f"{n}/{len(us)}")
    await m.answer(f"Envoyé à {n}/{len(us)} clients abonnés.")
