from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config import get_settings


class AdminOnlyMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        admin_ids = get_settings().admin_id_list
        if user is None:
            return None
        if user.id not in admin_ids:
            text = f"Нет доступа. Ваш Telegram ID: <code>{user.id}</code>"
            if isinstance(event, Message):
                await event.answer(text, parse_mode="HTML")
            elif isinstance(event, CallbackQuery):
                await event.answer("Нет доступа", show_alert=True)
                if event.message:
                    await event.message.answer(text, parse_mode="HTML")
            return None
        return await handler(event, data)
