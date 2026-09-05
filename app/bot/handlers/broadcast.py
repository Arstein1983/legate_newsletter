from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot.keyboards import confirm_broadcast_kb, pick_groups_kb, pick_templates_kb
from app.db import repo
from app.db.session import SessionLocal
from app.sender.campaign import is_campaign_running, start_campaign
from app.sender.client import admin_clients

router = Router()


@router.callback_query(F.data == "menu:broadcast")
async def cb_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if not callback.message:
        return
    admin = admin_clients.get(callback.from_user.id)
    if not await admin.is_authorized():
        await callback.message.answer(
            "Сначала войдите в свой аккаунт в «Настройках». "
            "Рассылка идёт от вашего Telegram, не от бота. У каждого админа своя сессия."
        )
        return
    if is_campaign_running(callback.from_user.id):
        await callback.message.answer(
            "У вас уже идёт рассылка. Дождитесь окончания или остановите её в настройках."
        )
        return
    async with SessionLocal() as session:
        groups = await repo.list_groups(session)
    if not groups:
        await callback.message.answer("Сначала создайте группу получателей.")
        return
    items = [(g.id, g.name, count) for g, count in groups]
    await callback.message.answer(
        "Выберите группу для рассылки.\nСообщения уйдут с вашего аккаунта Telegram.",
        reply_markup=pick_groups_kb(items, "bc:grp"),
    )


@router.callback_query(F.data.startswith("bc:grp:"))
async def cb_pick_group(callback: CallbackQuery) -> None:
    group_id = int(callback.data.split(":")[2])
    await callback.answer()
    if not callback.message:
        return
    async with SessionLocal() as session:
        templates = await repo.list_templates(session)
        group = await repo.get_group(session, group_id)
        _, total = await repo.list_recipients(session, group_id, limit=1)
    if not group:
        await callback.message.answer("Группа не найдена")
        return
    if total == 0:
        await callback.message.answer("В этой группе нет получателей.")
        return
    if not templates:
        await callback.message.answer("Сначала сохраните хотя бы одно сообщение-шаблон.")
        return
    items = [(t.id, t.title) for t in templates]
    await callback.message.answer(
        f"Группа: <b>{escape(group.name)}</b> ({total} чел.)\nВыберите сообщение:",
        reply_markup=pick_templates_kb(items, group_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("bc:tpl:"))
async def cb_pick_template(callback: CallbackQuery) -> None:
    _, _, group_id_s, template_id_s = callback.data.split(":")
    group_id = int(group_id_s)
    template_id = int(template_id_s)
    await callback.answer()
    if not callback.message:
        return
    async with SessionLocal() as session:
        group = await repo.get_group(session, group_id)
        template = await repo.get_template(session, template_id)
        _, total = await repo.list_recipients(session, group_id, limit=1)
        delay = await repo.get_setting(session, "send_delay_seconds", "4")
    admin = admin_clients.get(callback.from_user.id)
    me = await admin.me_label() or "ваш аккаунт"
    group_name = escape(group.name) if group else "?"
    tpl_name = escape(template.title) if template else "?"
    await callback.message.answer(
        f"Проверьте перед запуском:\n\n"
        f"От кого: <b>{escape(me)}</b>\n"
        f"Группа: <b>{group_name}</b> ({total})\n"
        f"Сообщение: <b>{tpl_name}</b>\n"
        f"Пауза между отправками: {escape(delay)} сек.\n\n"
        "У получателя должно быть открыто общение с вашим аккаунтом "
        "(или он есть в контактах). Иначе Telegram может отклонить сообщение.",
        reply_markup=confirm_broadcast_kb(group_id, template_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("bc:go:"))
async def cb_go(callback: CallbackQuery) -> None:
    _, _, group_id_s, template_id_s = callback.data.split(":")
    group_id = int(group_id_s)
    template_id = int(template_id_s)
    if not callback.message:
        await callback.answer()
        return
    result = await start_campaign(
        callback.bot,
        callback.from_user.id,
        callback.message.chat.id,
        group_id,
        template_id,
    )
    if result == "already_running":
        await callback.answer("У вас уже идёт рассылка", show_alert=True)
        return
    if result == "not_authorized":
        await callback.answer("Нет вашей сессии — войдите в настройках", show_alert=True)
        return
    if result == "empty":
        await callback.answer("Группа пуста", show_alert=True)
        return
    if result == "missing":
        await callback.answer("Группа или шаблон не найдены", show_alert=True)
        return
    await callback.answer("Запущено")
    await callback.message.answer("Рассылка запущена с вашего аккаунта. Прогресс придёт отдельными сообщениями.")
