from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from telethon.errors import (
    FloodWaitError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberBannedError,
    PhoneNumberFloodError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)

from app.bot.keyboards import cancel_fsm_kb, settings_kb
from app.bot.states import AuthFlow, DelayChange
from app.config import get_settings
from app.db import repo
from app.db.session import SessionLocal
from app.sender.campaign import is_campaign_running, request_cancel
from app.sender.client import admin_clients
from app.utils import status_ru

router = Router()


async def render_settings(target: Message, admin_id: int) -> None:
    admin = admin_clients.get(admin_id)
    authorized = await admin.is_authorized()
    me = await admin.me_label() if authorized else None
    async with SessionLocal() as session:
        delay = await repo.get_setting(session, "send_delay_seconds", str(get_settings().send_delay_seconds))
    account = escape(me) if me else "не авторизован"
    await target.answer(
        "⚙️ <b>Настройки</b>\n\n"
        f"Ваш аккаунт для рассылки: <b>{account}</b>\n"
        f"Пауза между сообщениями: <b>{escape(delay)}</b> сек.\n\n"
        "У каждого админа своя сессия. Рассылка идёт с вашего Telegram-аккаунта, бот только управляет процессом.",
        reply_markup=settings_kb(authorized, is_campaign_running(admin_id)),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "menu:settings")
async def cb_settings(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message:
        await render_settings(callback.message, callback.from_user.id)


@router.callback_query(F.data == "set:login")
async def cb_login(callback: CallbackQuery, state: FSMContext) -> None:
    admin = admin_clients.get(callback.from_user.id)
    if await admin.is_authorized():
        await callback.answer("Уже авторизованы", show_alert=True)
        return
    await state.set_state(AuthFlow.phone)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Введите номер телефона <b>вашего</b> аккаунта, от которого пойдёт рассылка.\n"
            "Формат: <code>+79001234567</code>\n\n"
            "Сессия сохранится только для вас — другие админы входят отдельно.",
            reply_markup=cancel_fsm_kb(),
            parse_mode="HTML",
        )


@router.message(AuthFlow.phone, F.text)
async def msg_phone(message: Message, state: FSMContext) -> None:
    phone = (message.text or "").strip()
    admin = admin_clients.get(message.from_user.id)
    try:
        await admin.request_code(phone)
    except PhoneNumberInvalidError:
        await message.answer("Некорректный номер. Попробуйте ещё раз.")
        return
    except PhoneNumberBannedError:
        await message.answer("Этот номер заблокирован в Telegram.")
        await state.clear()
        return
    except PhoneNumberFloodError:
        await message.answer("Слишком много запросов кода. Подождите и попробуйте позже.")
        await state.clear()
        return
    except FloodWaitError as exc:
        await message.answer(f"Telegram просит подождать {exc.seconds} сек.")
        return
    except Exception as exc:
        await message.answer(f"Не удалось отправить код: {exc}")
        return
    await state.set_state(AuthFlow.code)
    await message.answer(
        "Код придёт в Telegram (приложение, не этот бот). Пришлите его сюда.",
        reply_markup=cancel_fsm_kb(),
    )


@router.message(AuthFlow.code, F.text)
async def msg_code(message: Message, state: FSMContext) -> None:
    code = (message.text or "").replace(" ", "")
    admin = admin_clients.get(message.from_user.id)
    try:
        result = await admin.sign_in_code(code)
    except PhoneCodeInvalidError:
        await message.answer("Неверный код. Попробуйте ещё раз или нажмите «Отмена».")
        return
    except PhoneCodeExpiredError:
        await message.answer("Код истек. Начните вход заново через настройки.")
        await state.clear()
        return
    except SessionPasswordNeededError:
        result = "password"
    except Exception as exc:
        await message.answer(f"Ошибка входа: {exc}")
        return
    if result == "password":
        await state.set_state(AuthFlow.password)
        await message.answer("Включена облачная пароль (2FA). Введите пароль:", reply_markup=cancel_fsm_kb())
        return
    await state.clear()
    me = await admin.me_label() or "аккаунт"
    await message.answer(f"Вход выполнен: {me}. Рассылка будет идти от этого аккаунта.")


@router.message(AuthFlow.password, F.text)
async def msg_password(message: Message, state: FSMContext) -> None:
    admin = admin_clients.get(message.from_user.id)
    try:
        await admin.sign_in_password(message.text or "")
    except Exception as exc:
        await message.answer(f"Неверный пароль или ошибка: {exc}")
        return
    await state.clear()
    me = await admin.me_label() or "аккаунт"
    await message.answer(f"Вход выполнен: {me}.")


@router.callback_query(F.data == "set:logout")
async def cb_logout(callback: CallbackQuery) -> None:
    admin_id = callback.from_user.id
    if is_campaign_running(admin_id):
        await callback.answer("Сначала остановите рассылку", show_alert=True)
        return
    await admin_clients.get(admin_id).logout()
    await callback.answer("Ваша сессия удалена")
    if callback.message:
        await render_settings(callback.message, admin_id)


@router.callback_query(F.data == "set:delay")
async def cb_delay(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(DelayChange.value)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Введите паузу между сообщениями в секундах (от 1 до 60).\n"
            "Меньшая пауза быстрее, но Telegram чаще ограничивает аккаунт.",
            reply_markup=cancel_fsm_kb(),
        )


@router.message(DelayChange.value, F.text)
async def msg_delay(message: Message, state: FSMContext) -> None:
    try:
        value = float((message.text or "").replace(",", "."))
    except ValueError:
        await message.answer("Введите число, например 4")
        return
    if not 1 <= value <= 60:
        await message.answer("Допустимо от 1 до 60 секунд.")
        return
    async with SessionLocal() as session:
        await repo.set_setting(session, "send_delay_seconds", str(value))
    await state.clear()
    await message.answer(f"Пауза установлена: {value} сек.")
    await render_settings(message, message.from_user.id)


@router.callback_query(F.data == "set:stop")
async def cb_stop(callback: CallbackQuery) -> None:
    if request_cancel(callback.from_user.id):
        await callback.answer("Остановка после текущего сообщения")
        if callback.message:
            await callback.message.answer("Ваша рассылка будет остановлена.")
        return
    await callback.answer("Сейчас у вас ничего не отправляется", show_alert=True)


@router.callback_query(F.data == "menu:history")
async def cb_history(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if not callback.message:
        return
    async with SessionLocal() as session:
        campaigns = await repo.list_campaigns(session, limit=10)
    if not campaigns:
        await callback.message.answer("Пока не было рассылок.")
        return
    lines = ["📊 <b>Последние рассылки</b>\n"]
    for item in campaigns:
        group_name = item.group.name if item.group else "?"
        tpl_name = item.template.title if item.template else "?"
        when = item.started_at.strftime("%d.%m %H:%M") if item.started_at else ""
        lines.append(
            f"#{item.id} {when} — {status_ru(item.status)}\n"
            f"{escape(group_name)} / {escape(tpl_name)}\n"
            f"✅ {item.sent}  ❌ {item.failed}  из {item.total}\n"
        )
    await callback.message.answer("\n".join(lines), parse_mode="HTML")
