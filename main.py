import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommandScopeDefault, MenuButtonDefault

from app.bot.handlers import setup_routers
from app.bot.middlewares import AdminOnlyMiddleware
from app.config import MEDIA_DIR, SESSIONS_DIR, get_settings
from app.db.session import init_db
from app.sender.client import admin_clients


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    await init_db()
    try:
        await admin_clients.start_all_authorized()
    except Exception:
        logging.exception("Could not restore Telegram user sessions; log in via bot settings")

    settings = get_settings()
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    router = setup_routers()
    router.message.middleware(AdminOnlyMiddleware())
    router.callback_query.middleware(AdminOnlyMiddleware())
    dp.include_router(router)

    await bot.delete_my_commands(scope=BotCommandScopeDefault())
    await bot.set_chat_menu_button(menu_button=MenuButtonDefault())

    logging.getLogger(__name__).info("Bot started")
    try:
        await dp.start_polling(bot)
    finally:
        await admin_clients.disconnect_all()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
