from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from app.config import SESSIONS_DIR, get_settings

SESSION_FILE = SESSIONS_DIR / "admin"


class AdminClient:
    def __init__(self) -> None:
        self.client: Optional[TelegramClient] = None
        self._lock = asyncio.Lock()
        self.pending_phone: Optional[str] = None
        self.pending_phone_code_hash: Optional[str] = None

    def _build_client(self) -> TelegramClient:
        settings = get_settings()
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        return TelegramClient(
            str(SESSION_FILE),
            settings.telegram_api_id,
            settings.telegram_api_hash,
            device_model="Newsletter Bot",
            app_version="1.0",
        )

    async def start_if_authorized(self) -> bool:
        async with self._lock:
            if self.client and self.client.is_connected() and await self.client.is_user_authorized():
                return True
            if self.client:
                await self.client.disconnect()
                self.client = None
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
                path = Path(str(SESSION_FILE) + suffix)
                if path.exists():
                    path.unlink(missing_ok=True)
            session_path = Path(str(SESSION_FILE) + ".session")
            if session_path.exists():
                session_path.unlink(missing_ok=True)

    async def disconnect(self) -> None:
        if self.client:
            await self.client.disconnect()
            self.client = None


admin_client = AdminClient()
