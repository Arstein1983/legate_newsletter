from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from aiogram import Bot
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    InputUserDeactivatedError,
    PeerFloodError,
    UserDeactivatedBanError,
    UserDeactivatedError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
    UserPrivacyRestrictedError,
)
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.types import InputPhoneContact

from app.db import repo
from app.db.session import SessionLocal
from app.sender.client import AdminClient, admin_clients
from app.utils import recipient_label

logger = logging.getLogger(__name__)

_campaign_tasks: dict[int, asyncio.Task] = {}
_cancel_events: dict[int, asyncio.Event] = {}
_lock = asyncio.Lock()


def is_campaign_running(admin_id: Optional[int] = None) -> bool:
    if admin_id is None:
        return any(task is not None and not task.done() for task in _campaign_tasks.values())
    task = _campaign_tasks.get(admin_id)
    return task is not None and not task.done()


def request_cancel(admin_id: int) -> bool:
    if not is_campaign_running(admin_id):
        return False
    event = _cancel_events.get(admin_id)
    if event is None:
        return False
    event.set()
    return True


async def start_campaign(
    bot: Bot,
    admin_user_id: int,
    admin_chat_id: int,
    group_id: int,
    template_id: int,
) -> str:
    async with _lock:
        if is_campaign_running(admin_user_id):
            return "already_running"

        admin = admin_clients.get(admin_user_id)
        if not await admin.is_authorized():
            return "not_authorized"

        async with SessionLocal() as session:
            group = await repo.get_group(session, group_id)
            template = await repo.get_template(session, template_id)
            recipients = await repo.get_all_recipients(session, group_id)
            if not group or not template:
                return "missing"
            if not recipients:
                return "empty"
            campaign = await repo.create_campaign(session, group_id, template_id, total=len(recipients))
            campaign_id = campaign.id
            delay_raw = await repo.get_setting(session, "send_delay_seconds", "4")

        delay = max(1.0, float(delay_raw))
        cancel_event = asyncio.Event()
        _cancel_events[admin_user_id] = cancel_event
        _campaign_tasks[admin_user_id] = asyncio.create_task(
            _run_campaign(bot, admin, admin_chat_id, admin_user_id, campaign_id, delay, cancel_event),
            name=f"campaign-{campaign_id}-admin-{admin_user_id}",
        )
        return f"started:{campaign_id}"


async def _resolve_entity(client: TelegramClient, recipient) -> object:
    if recipient.username:
        return await client.get_entity(recipient.username)
    if recipient.phone:
        first_name = recipient.display_name or recipient.phone
        result = await client(
            ImportContactsRequest(
                [
                    InputPhoneContact(
                        client_id=0,
                        phone=recipient.phone,
                        first_name=first_name[:64],
                        last_name="",
                    )
                ]
            )
        )
        if result.users:
            return result.users[0]
        raise RuntimeError(
            "Не удалось найти пользователя по номеру. Добавьте контакт вручную или используйте @username."
        )
    raise RuntimeError("У получателя нет username и телефона")


async def _send_to_entity(client: TelegramClient, entity, template) -> None:
    text = template.text or ""
    media_path = template.media_path
    if media_path and Path(media_path).exists():
        if text and len(text) > 1024:
            await client.send_file(entity, media_path)
            await client.send_message(entity, text[:4096], parse_mode="html")
            return
        await client.send_file(entity, media_path, caption=text or None, parse_mode="html")
        return
    if not text:
        raise RuntimeError("Пустой шаблон")
    await client.send_message(entity, text[:4096], parse_mode="html")


def _error_text(exc: Exception) -> str:
    mapping = {
        UserPrivacyRestrictedError: "Пользователь ограничил входящие сообщения",
        UsernameNotOccupiedError: "Username не существует",
        UsernameInvalidError: "Некорректный username",
        InputUserDeactivatedError: "Аккаунт удалён",
        UserDeactivatedError: "Аккаунт деактивирован",
        UserDeactivatedBanError: "Аккаунт заблокирован",
        PeerFloodError: "Telegram ограничил массовую отправку (PeerFlood)",
    }
    for exc_type, message in mapping.items():
        if isinstance(exc, exc_type):
            return message
    return str(exc)[:500]


async def _run_campaign(
    bot: Bot,
    admin: AdminClient,
    admin_chat_id: int,
    admin_user_id: int,
    campaign_id: int,
    delay: float,
    cancel_event: asyncio.Event,
) -> None:
    sent = 0
    failed = 0
    stopped = False
    client = admin.client
    assert client is not None

    async with SessionLocal() as session:
        campaign = await repo.get_campaign(session, campaign_id)
        if not campaign:
            return
        recipients = list(await repo.get_all_recipients(session, campaign.group_id))
        template = await repo.get_template(session, campaign.template_id)
        total = len(recipients)

    if not template:
        await bot.send_message(admin_chat_id, "Шаблон сообщения не найден, рассылка отменена.")
        async with SessionLocal() as session:
            await repo.update_campaign_progress(session, campaign_id, status="failed", finished=True)
        return

    me = await admin.me_label() or "ваш аккаунт"
    progress = await bot.send_message(
        admin_chat_id,
        f"📣 Рассылка #{campaign_id} запущена.\n"
        f"Отправка идёт с аккаунта <b>{me}</b>, не от бота.\n"
        f"Прогресс: 0/{total}",
        parse_mode="HTML",
    )

    try:
        for index, recipient in enumerate(recipients, start=1):
            if cancel_event.is_set():
                stopped = True
                break

            label = recipient_label(recipient.username, recipient.phone, recipient.display_name)
            try:
                entity = await _resolve_entity(client, recipient)
                await _send_to_entity(client, entity, template)
                sent += 1
                async with SessionLocal() as session:
                    await repo.add_campaign_log(session, campaign_id, recipient.id, "sent")
                    await repo.update_campaign_progress(session, campaign_id, sent=sent, failed=failed)
            except FloodWaitError as exc:
                wait_for = int(exc.seconds) + 1
                await bot.send_message(
                    admin_chat_id,
                    f"⏳ Telegram просит подождать {wait_for} сек. Продолжаю после паузы.",
                )
                await asyncio.sleep(wait_for)
                try:
                    entity = await _resolve_entity(client, recipient)
                    await _send_to_entity(client, entity, template)
                    sent += 1
                    async with SessionLocal() as session:
                        await repo.add_campaign_log(session, campaign_id, recipient.id, "sent")
                        await repo.update_campaign_progress(session, campaign_id, sent=sent, failed=failed)
                except Exception as retry_exc:
                    failed += 1
                    async with SessionLocal() as session:
                        await repo.add_campaign_log(
                            session, campaign_id, recipient.id, "failed", _error_text(retry_exc)
                        )
                        await repo.update_campaign_progress(session, campaign_id, sent=sent, failed=failed)
            except PeerFloodError as exc:
                failed += 1
                async with SessionLocal() as session:
                    await repo.add_campaign_log(session, campaign_id, recipient.id, "failed", _error_text(exc))
                    await repo.update_campaign_progress(
                        session, campaign_id, sent=sent, failed=failed, status="failed", finished=True
                    )
                await bot.send_message(
                    admin_chat_id,
                    "⛔ Telegram ограничил массовую отправку. Рассылка остановлена.",
                )
                stopped = True
                break
            except Exception as exc:
                logger.exception("Send failed for %s (admin %s)", label, admin_user_id)
                failed += 1
                async with SessionLocal() as session:
                    await repo.add_campaign_log(session, campaign_id, recipient.id, "failed", _error_text(exc))
                    await repo.update_campaign_progress(session, campaign_id, sent=sent, failed=failed)

            if index % 3 == 0 or index == total:
                try:
                    await progress.edit_text(
                        f"📣 Рассылка #{campaign_id}\n"
                        f"Прогресс: {index}/{total}\n"
                        f"✅ Отправлено: {sent}\n"
                        f"❌ Ошибки: {failed}"
                    )
                except Exception:
                    pass

            if index < total and not cancel_event.is_set():
                await asyncio.sleep(delay)

        status = "cancelled" if stopped and cancel_event.is_set() else "failed" if stopped else "completed"
        if status != "failed":
            async with SessionLocal() as session:
                await repo.update_campaign_progress(
                    session, campaign_id, sent=sent, failed=failed, status=status, finished=True
                )

        if status == "cancelled":
            text = f"⏹ Рассылка #{campaign_id} остановлена.\n✅ {sent}  ❌ {failed}  из {total}"
        elif status == "completed":
            text = f"✅ Рассылка #{campaign_id} завершена.\n✅ {sent}  ❌ {failed}  из {total}"
        else:
            text = f"⛔ Рассылка #{campaign_id} прервана.\n✅ {sent}  ❌ {failed}  из {total}"
        await bot.send_message(admin_chat_id, text)
    except Exception:
        logger.exception("Campaign crashed (admin %s)", admin_user_id)
        async with SessionLocal() as session:
            await repo.update_campaign_progress(
                session, campaign_id, sent=sent, failed=failed, status="failed", finished=True
            )
        await bot.send_message(admin_chat_id, f"⛔ Рассылка #{campaign_id} завершилась с ошибкой.")
    finally:
        _campaign_tasks.pop(admin_user_id, None)
        _cancel_events.pop(admin_user_id, None)
