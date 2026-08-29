from aiogram import F, Router

from app.bot.handlers import broadcast, groups, settings, start, templates


def setup_routers() -> Router:
    root = Router()
    root.message.filter(F.chat.type == "private")
    root.callback_query.filter(F.message.chat.type == "private")
    root.include_router(start.router)
    root.include_router(groups.router)
    root.include_router(templates.router)
    root.include_router(broadcast.router)
    root.include_router(settings.router)
    return root
