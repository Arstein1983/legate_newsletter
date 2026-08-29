from pathlib import Path
from typing import Optional

from aiogram.types import Message

from app.config import MEDIA_DIR


def extract_text(message: Message) -> Optional[str]:
    html = getattr(message, "html_text", None)
    if html:
        return html
    return message.caption or message.text


async def save_media(message: Message, template_id: int) -> tuple[Optional[str], Optional[str]]:
    source = None
    media_type = None
    ext = ""
    if message.photo:
        source, media_type, ext = message.photo[-1], "photo", ".jpg"
    elif message.video:
        source, media_type, ext = message.video, "video", ".mp4"
    elif message.animation:
        source, media_type, ext = message.animation, "animation", ".mp4"
    elif message.audio:
        source, media_type, ext = message.audio, "audio", Path(message.audio.file_name or "audio.mp3").suffix or ".mp3"
    elif message.voice:
        source, media_type, ext = message.voice, "voice", ".ogg"
    elif message.document:
        source, media_type = message.document, "document"
        ext = Path(message.document.file_name or "").suffix

    if source is None or media_type is None:
        return None, None

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    path = MEDIA_DIR / f"{template_id}_{media_type}{ext}"
    await message.bot.download(source, destination=path)
    return str(path), media_type
