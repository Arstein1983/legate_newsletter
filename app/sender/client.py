from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from app.config import SESSIONS_DIR, get_settings

logger = logging.getLogger(__name__)


class AdminClient:
    """Telethon-сессия одного админа (по Telegram user id)."""

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        self.client: Optional[TelegramClient] = None
        self._lock = asyncio.Lock()
        self.pending_phone: Optional[str] = None
        self.pending_phone_code_hash: Optional[str] = None

    @property
    def session_path(self) -> Path:
        return SESSIONS_DIR / f"admin_{self.user_id}"

    def _build_client(self) -> TelegramClient:
        settings = get_settings()
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        return TelegramClient(
            str(self.session_path),
            settings.telegram_api_id,
            settings.telegram_api_hash,
            device_model=f"Newsletter Bot ({self.user_id})",
            app_version="1.0",
        )

    async def start_if_authorized(self) -> bool:
        async with self._lock:
            if self.client and self.client.is_connected() and await self.client.is_user_authorized():
                return True
            if self.client:
                await self.client.disconnect()
                self.client = None
            session_file = Path(str(self.session_path) + ".session")
            if not session_file.exists():
                return False
            client = self._build_client()
            await client.connect()
            if await client.is_user_authorized():
                self.client = client
                return True
            await client.disconnect()
            return False

    async def is_authorized(self) -> bool:
        if self.client and self.client.is_connected():
            return await self.client.is_user_authorized()
        return await self.start_if_authorized()

    async def me_label(self) -> Optional[str]:
        if not await self.is_authorized() or not self.client:
            return None
        me = await self.client.get_me()
        username = f"@{me.username}" if me.username else ""
        name = " ".join(part for part in [me.first_name, me.last_name] if part)
        return f"{name} {username}".strip() or str(me.id)

    async def request_code(self, phone: str) -> None:
        async with self._lock:
            if self.client:
                await self.client.disconnect()
            self.client = self._build_client()
            await self.client.connect()
            sent = await self.client.send_code_request(phone)
            self.pending_phone = phone
            self.pending_phone_code_hash = sent.phone_code_hash

    async def sign_in_code(self, code: str) -> str:
        if not self.client or not self.pending_phone or not self.pending_phone_code_hash:
            raise RuntimeError("Сначала запросите код")
        try:
            await self.client.sign_in(
                phone=self.pending_phone,
                code=code.strip(),
                phone_code_hash=self.pending_phone_code_hash,
            )
            return "ok"
        except SessionPasswordNeededError:
            return "password"

    async def sign_in_password(self, password: str) -> None:
        if not self.client:
            raise RuntimeError("Клиент не подключён")
        await self.client.sign_in(password=password)

    async def logout(self) -> None:
        async with self._lock:
            if self.client:
                try:
                    if await self.client.is_user_authorized():
                        await self.client.log_out()
                    else:
                        await self.client.disconnect()
                except Exception:
                    try:
                        await self.client.disconnect()
                    except Exception:
                        pass
                self.client = None
            for suffix in ("", ".session", ".session-journal"):
                path = Path(str(self.session_path) + suffix)
                if path.exists():
                    path.unlink(missing_ok=True)

    async def disconnect(self) -> None:
        if self.client:
            await self.client.disconnect()
            self.client = None


class AdminClientManager:
    """Хранит личные Telethon-сессии для каждого админа из ADMIN_IDS."""

    def __init__(self) -> None:
        self._clients: dict[int, AdminClient] = {}
        self._lock = asyncio.Lock()

    def get(self, user_id: int) -> AdminClient:
        if user_id not in self._clients:
            self._clients[user_id] = AdminClient(user_id)
        return self._clients[user_id]

    async def start_all_authorized(self) -> None:
        """Поднимает уже сохранённые сессии админов при старте бота."""
        settings = get_settings()
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        await self._migrate_legacy_session(settings.admin_id_list)

        for user_id in settings.admin_id_list:
            client = self.get(user_id)
            try:
                ok = await client.start_if_authorized()
                if ok:
                    logger.info("Restored Telethon session for admin %s", user_id)
            except Exception:
                logger.exception("Could not restore session for admin %s", user_id)

    async def _migrate_legacy_session(self, admin_ids: list[int]) -> None:
        """Старый файл sessions/admin.session → sessions/admin_<id>.session для первого админа."""
        legacy = SESSIONS_DIR / "admin.session"
        if not legacy.exists() or not admin_ids:
            return
        target = SESSIONS_DIR / f"admin_{admin_ids[0]}.session"
        if target.exists():
            return
        try:
            legacy.rename(target)
            journal = SESSIONS_DIR / "admin.session-journal"
            if journal.exists():
                journal.rename(SESSIONS_DIR / f"admin_{admin_ids[0]}.session-journal")
            logger.info("Migrated legacy session to admin_%s.session", admin_ids[0])
        except Exception:
            logger.exception("Failed to migrate legacy Telethon session")

    async def disconnect_all(self) -> None:
        for client in list(self._clients.values()):
            await client.disconnect()


admin_clients = AdminClientManager()
