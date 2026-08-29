import re
from dataclasses import dataclass
from typing import Optional


USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")
PHONE_RE = re.compile(r"^\+?\d{10,15}$")


@dataclass
class ParsedRecipient:
    username: Optional[str] = None
    phone: Optional[str] = None
    display_name: Optional[str] = None


def parse_recipient_line(raw: str) -> ParsedRecipient:
    line = raw.strip()
    if not line or line.startswith("#"):
        raise ValueError("empty")

    display_name = None
    if "," in line or ";" in line:
        parts = [part.strip() for part in re.split(r"[,;]", line) if part.strip()]
        line = parts[0]
        if len(parts) > 1:
            display_name = parts[1]

    if line.startswith("https://t.me/") or line.startswith("http://t.me/") or line.startswith("t.me/"):
        line = line.split("t.me/", 1)[1].split("?", 1)[0].split("/", 1)[0]

    if line.startswith("@"):
        line = line[1:]

    if USERNAME_RE.fullmatch(line):
        return ParsedRecipient(username=line, display_name=display_name)

    phone = normalize_phone(line)
    if phone:
        return ParsedRecipient(phone=phone, display_name=display_name)

    raise ValueError("invalid")


def normalize_phone(value: str) -> Optional[str]:
    digits = re.sub(r"\D", "", value)
    if not digits:
        return None
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if 10 <= len(digits) <= 15:
        phone = "+" + digits
        if PHONE_RE.fullmatch(phone):
            return phone
    return None


def recipient_label(username: Optional[str], phone: Optional[str], display_name: Optional[str] = None) -> str:
    if username:
        ident = f"@{username}"
    elif phone:
        ident = phone
    else:
        ident = "?"
    if display_name:
        return f"{display_name} ({ident})"
    return ident


def status_ru(status: str) -> str:
    return {
        "running": "идёт",
        "completed": "завершена",
        "cancelled": "остановлена",
        "failed": "ошибка",
    }.get(status, status)
