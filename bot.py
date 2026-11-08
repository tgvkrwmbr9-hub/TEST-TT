import asyncio
import logging
import sys
import time
from logging.handlers import RotatingFileHandler

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery

import admin
import database as db
import handlers
from config import ADMIN_IDS, BOT_TOKEN, LOGS, SUPPORT

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


async def main():
    LOGS.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[RotatingFileHandler(LOGS / "bot.log", maxBytes=2_000_000, backupCount=5), logging.StreamHandler()])
    if not BOT_TOKEN or not ADMIN_IDS:
        sys.exit("Configure BOT_TOKEN et ADMIN_ID dans le fichier .env")
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
    log.info("STYCH TYNY démarré")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
