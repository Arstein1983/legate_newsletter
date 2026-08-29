from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from aiogram import Bot
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
from app.sender.client import admin_client
from app.utils import recipient_label

logger = logging.getLogger(__name__)

_campaign_task: Optional[asyncio.Task] = None
_cancel_event = asyncio.Event()
_lock = asyncio.Lock()


def is_campaign_running() -> bool:
    return _campaign_task is not None and not _campaign_task.done()


def request_cancel() -> bool:
    if not is_campaign_running():
        return False
    _cancel_event.set()
    return True


async def start_campaign(bot: Bot, admin_chat_id: int, group_id: int, template_id: int) -> str:
    async with _lock:
        if is_campaign_running():
            return "already_running"
        if not await admin_client.is_authorized():
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
        _cancel_event.clear()
        global _campaign_task
        _campaign_task = asyncio.create_task(
            _run_campaign(bot, admin_chat_id, campaign_id, delay),
            name=f"campaign-{campaign_id}",
        )
        return f"started:{campaign_id}"


async def _resolve_entity(recipient) -> object:
    client = admin_client.client
    assert client is not None
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
        raise RuntimeError("Не удалось найти пользователя по номеру. Добавьте контакт вручную или используйте @username.")
    raise RuntimeError("У получателя нет username и телефона")


async def _send_to_entity(entity, template) -> None:
    client = admin_client.client
    assert client is not None
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


async def _run_campaign(bot: Bot, admin_chat_id: int, campaign_id: int, delay: float) -> None:
    sent = 0
    failed = 0
    stopped = False

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

    progress = await bot.send_message(
        admin_chat_id,
        f"📣 Рассылка #{campaign_id} запущена.\nОтправка идёт с вашего аккаунта, не от бота.\nПрогресс: 0/{total}",
    )

    try:
        for index, recipient in enumerate(recipients, start=1):
            if _cancel_event.is_set():
                stopped = True
                break

            label = recipient_label(recipient.username, recipient.phone, recipient.display_name)
            try:
                entity = await _resolve_entity(recipient)
                await _send_to_entity(entity, template)
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
                    entity = await _resolve_entity(recipient)
                    await _send_to_entity(entity, template)
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
                logger.exception("Send failed for %s", label)
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

            if index < total and not _cancel_event.is_set():
                await asyncio.sleep(delay)

        status = "cancelled" if stopped and _cancel_event.is_set() else "failed" if stopped else "completed"
        if status == "failed":
            pass
        else:
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
        logger.exception("Campaign crashed")
        async with SessionLocal() as session:
            await repo.update_campaign_progress(
                session, campaign_id, sent=sent, failed=failed, status="failed", finished=True
            )
        await bot.send_message(admin_chat_id, f"⛔ Рассылка #{campaign_id} завершилась с ошибкой.")
