import asyncio
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery

import admin
import backup
import database as db
import handlers
from config import ADMIN_IDS, BOT_TOKEN, DATA, DB_PATH, LOGS, SUPPORT

log = logging.getLogger("stych")


class Guard(BaseMiddleware):
    """Enregistre l'utilisateur, bloque les bannis et limite le spam."""
    def __init__(self):
        self.hits = {}

    async def __call__(self, handler, event, data):
        u = event.from_user
        if u and not u.is_bot:
            n = time.time()
            self.hits[u.id] = [t for t in self.hits.get(u.id, []) if n - t < 5] + [n]
            if len(self.hits[u.id]) > 10 and u.id not in ADMIN_IDS:
                return
            await db.upsert_user(u)
            row = await db.one("SELECT banned FROM users WHERE id=?", (u.id,))
            if row and row["banned"] and u.id not in ADMIN_IDS:
                txt = "🚫 Accès suspendu. Contacte-moi sur Telegram" + (f" : @{SUPPORT}" if SUPPORT else ".")
                if isinstance(event, CallbackQuery):
                    await event.answer(txt, show_alert=True)
                else:
                    await event.answer(txt)
                return
        return await handler(event, data)


async def backup_loop(bot):
    """Chaque nuit à 03:30 UTC : sauvegarde + envoi du fichier en message privé aux admins."""
    while True:
        n = time.time()
        nxt = n // 86400 * 86400 + 3.5 * 3600
        if nxt <= n:
            nxt += 86400
        await asyncio.sleep(nxt - n)
        try:
            await admin.make_backup(bot, ADMIN_IDS)
        except Exception:
            log.exception("Sauvegarde quotidienne en échec")


async def main():
    LOGS.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[RotatingFileHandler(LOGS / "bot.log", maxBytes=2_000_000, backupCount=5), logging.StreamHandler()])
    if not BOT_TOKEN or not ADMIN_IDS:
        sys.exit("Configure BOT_TOKEN et ADMIN_ID dans le fichier .env")
    mount = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    if os.getenv("RAILWAY_ENVIRONMENT") and (not mount or not str(DATA).startswith(mount)):
        sys.exit("Railway : ajoute un Volume monté sur /data ET la variable DATA_DIR=/data, "
                 "sinon la base serait effacée à chaque déploiement.")
    db.init()  # crée la base au premier démarrage, conserve tout ensuite
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(Guard())
    dp.callback_query.middleware(Guard())

    @dp.error()
    async def on_error(event):
        log.exception("Erreur : %s", event.exception)
        return True

    dp.include_router(admin.r)
    dp.include_router(handlers.r)
    try:
        await asyncio.to_thread(backup.main)  # copie de sécurité à chaque démarrage / mise à jour
    except Exception:
        log.exception("Sauvegarde de démarrage impossible")
    task = asyncio.create_task(backup_loop(bot))
    log.info("STYCH TYNY démarré")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
