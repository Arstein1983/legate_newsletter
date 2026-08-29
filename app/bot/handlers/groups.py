from html import escape
from math import ceil

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import (
    cancel_fsm_kb,
    confirm_delete_group_kb,
    done_kb,
    group_view_kb,
    groups_kb,
    recipients_kb,
)
from app.bot.states import GroupAddRecipients, GroupCreate, GroupImport
from app.db import repo
from app.db.session import SessionLocal
from app.sender.campaign import is_campaign_running
from app.utils import parse_recipient_line, recipient_label

router = Router()
PAGE_SIZE = 8


async def render_groups(message: Message) -> None:
    async with SessionLocal() as session:
        groups = await repo.list_groups(session)
    items = [(g.id, g.name, count) for g, count in groups]
    await message.answer("👥 Группы получателей:", reply_markup=groups_kb(items))


async def render_group(message: Message, group_id: int) -> None:
    async with SessionLocal() as session:
        group = await repo.get_group(session, group_id)
        recipients, total = await repo.list_recipients(session, group_id, offset=0, limit=5)
    if not group:
        await message.answer("Группа не найдена")
        return
    preview = "\n".join(
        f"• {escape(recipient_label(r.username, r.phone, r.display_name))}" for r in recipients
    ) or "пока пусто"
    extra = f"\n…и ещё {total - 5}" if total > 5 else ""
    await message.answer(
        f"<b>{escape(group.name)}</b>\nПолучателей: {total}\n\n{preview}{extra}",
        reply_markup=group_view_kb(group_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "menu:groups")
async def cb_groups(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message:
        await render_groups(callback.message)


@router.callback_query(F.data == "grp:new")
async def cb_new_group(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(GroupCreate.name)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Введите название группы:", reply_markup=cancel_fsm_kb())


@router.message(GroupCreate.name)
async def msg_group_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name or len(name) > 255:
        await message.answer("Название не должно быть пустым и длиннее 255 символов.")
        return
    async with SessionLocal() as session:
        group = await repo.create_group(session, name)
    await state.clear()
    await message.answer(f"Группа «{group.name}» создана.")
    await render_group(message, group.id)


@router.callback_query(F.data.startswith("grp:view:"))
async def cb_view_group(callback: CallbackQuery) -> None:
    group_id = int(callback.data.split(":")[2])
    await callback.answer()
    if callback.message:
        await render_group(callback.message, group_id)


@router.callback_query(F.data.startswith("grp:add:"))
async def cb_add_recipients(callback: CallbackQuery, state: FSMContext) -> None:
    group_id = int(callback.data.split(":")[2])
    await state.set_state(GroupAddRecipients.waiting)
    await state.update_data(group_id=group_id)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Пришлите получателей — по одному в строке:\n"
            "• <code>@username</code>\n"
            "• <code>+79001234567</code>\n"
            "• <code>@tag, Имя</code> или <code>+79001234567, Имя</code>\n\n"
            "Можно несколько строк сразу. Когда закончите — нажмите «Готово».",
            reply_markup=done_kb(),
            parse_mode="HTML",
        )


@router.message(GroupAddRecipients.waiting, F.text)
async def msg_add_recipients(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    group_id = data["group_id"]
    added = 0
    duplicates = 0
    invalid = 0
    async with SessionLocal() as session:
        for raw in (message.text or "").splitlines():
            try:
                parsed = parse_recipient_line(raw)
            except ValueError:
                if raw.strip():
                    invalid += 1
                continue
            _, status = await repo.add_recipient(
                session, group_id, parsed.username, parsed.phone, parsed.display_name
            )
            if status == "ok":
                added += 1
            else:
                duplicates += 1
    await message.answer(
        f"Добавлено: {added}\nУже были: {duplicates}\nНе распознано: {invalid}",
        reply_markup=done_kb(),
    )


@router.message(GroupAddRecipients.waiting)
async def msg_add_recipients_wrong(message: Message) -> None:
    await message.answer("Пришлите текст: @username или номер телефона. Когда закончите — «Готово».")


@router.callback_query(F.data == "fsm:done", GroupAddRecipients.waiting)
async def cb_add_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    await callback.answer()
    if callback.message:
        await render_group(callback.message, data["group_id"])


@router.callback_query(F.data.startswith("grp:import:"))
async def cb_import(callback: CallbackQuery, state: FSMContext) -> None:
    group_id = int(callback.data.split(":")[2])
    await state.set_state(GroupImport.waiting_file)
    await state.update_data(group_id=group_id)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Пришлите .txt или .csv файл. Одна строка — один получатель:\n"
            "<code>@username</code>\n"
            "<code>+79001234567</code>\n"
            "<code>username,Имя</code>",
            reply_markup=cancel_fsm_kb(),
            parse_mode="HTML",
        )


@router.message(GroupImport.waiting_file, F.document)
async def msg_import_file(message: Message, state: FSMContext) -> None:
    document = message.document
    name = (document.file_name or "").lower()
    if not name.endswith((".txt", ".csv")):
        await message.answer("Нужен файл .txt или .csv")
        return
    file = await message.bot.download(document)
    content = file.read().decode("utf-8-sig", errors="replace")
    data = await state.get_data()
    group_id = data["group_id"]
    added = 0
    duplicates = 0
    invalid = 0
    async with SessionLocal() as session:
        for raw in content.splitlines():
            try:
                parsed = parse_recipient_line(raw)
            except ValueError:
                if raw.strip() and not raw.strip().lower().startswith(("username", "phone", "tag")):
                    invalid += 1
                continue
            _, status = await repo.add_recipient(
                session, group_id, parsed.username, parsed.phone, parsed.display_name
            )
            if status == "ok":
                added += 1
            else:
                duplicates += 1
    await state.clear()
    await message.answer(f"Импорт готов. Добавлено: {added}, уже были: {duplicates}, ошибок: {invalid}")
    await render_group(message, group_id)


@router.message(GroupImport.waiting_file)
async def msg_import_wrong(message: Message) -> None:
    await message.answer("Пришлите файл .txt или .csv, или нажмите «Отмена».")


@router.callback_query(F.data.startswith("grp:recs:"))
async def cb_recipients(callback: CallbackQuery) -> None:
    _, _, group_id_s, page_s = callback.data.split(":")
    group_id = int(group_id_s)
    page = int(page_s)
    async with SessionLocal() as session:
        rows, total = await repo.list_recipients(session, group_id, offset=page * PAGE_SIZE, limit=PAGE_SIZE)
        group = await repo.get_group(session, group_id)
    items = [(r.id, recipient_label(r.username, r.phone, r.display_name)[:40]) for r in rows]
    pages = max(1, ceil(total / PAGE_SIZE)) if total else 1
    await callback.answer()
    if callback.message:
        title = group.name if group else "Группа"
        await callback.message.answer(
            f"Получатели «{title}»: {total}",
            reply_markup=recipients_kb(group_id, items, page, pages),
        )


@router.callback_query(F.data.startswith("rec:del:"))
async def cb_del_recipient(callback: CallbackQuery) -> None:
    _, _, rid_s, page_s = callback.data.split(":")
    recipient_id = int(rid_s)
    page = int(page_s)
    async with SessionLocal() as session:
        group_id = await repo.delete_recipient(session, recipient_id)
    await callback.answer("Удалено")
    if not group_id or not callback.message:
        return
    async with SessionLocal() as session:
        rows, total = await repo.list_recipients(session, group_id, offset=page * PAGE_SIZE, limit=PAGE_SIZE)
    if not rows and page > 0:
        page -= 1
        async with SessionLocal() as session:
            rows, total = await repo.list_recipients(session, group_id, offset=page * PAGE_SIZE, limit=PAGE_SIZE)
    items = [(r.id, recipient_label(r.username, r.phone, r.display_name)[:40]) for r in rows]
    pages = max(1, ceil(total / PAGE_SIZE)) if total else 1
    await callback.message.answer(
        f"Получатели: {total}",
        reply_markup=recipients_kb(group_id, items, page, pages),
    )


@router.callback_query(F.data.startswith("grp:del:") & ~F.data.startswith("grp:delc:"))
async def cb_del_group(callback: CallbackQuery) -> None:
    group_id = int(callback.data.split(":")[2])
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Удалить группу вместе со всеми получателями?",
            reply_markup=confirm_delete_group_kb(group_id),
        )


@router.callback_query(F.data.startswith("grp:delc:"))
async def cb_del_group_confirm(callback: CallbackQuery) -> None:
    if is_campaign_running():
        await callback.answer("Дождитесь окончания рассылки", show_alert=True)
        return
    group_id = int(callback.data.split(":")[2])
    async with SessionLocal() as session:
        await repo.delete_group(session, group_id)
    await callback.answer("Группа удалена")
    if callback.message:
        await render_groups(callback.message)
