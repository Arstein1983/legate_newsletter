from html import escape
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.bot.keyboards import cancel_fsm_kb, template_view_kb, templates_kb
from app.bot.media import extract_text, save_media
from app.bot.states import TemplateCreate
from app.db import repo
from app.db.session import SessionLocal
from app.sender.campaign import is_campaign_running

router = Router()


async def render_templates(message: Message) -> None:
    async with SessionLocal() as session:
        templates = await repo.list_templates(session)
    items = [(t.id, t.title) for t in templates]
    await message.answer("✉️ Сохранённые сообщения для рассылки:", reply_markup=templates_kb(items))


@router.callback_query(F.data == "menu:templates")
async def cb_templates(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message:
        await render_templates(callback.message)


@router.callback_query(F.data == "tpl:new")
async def cb_new_template(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TemplateCreate.title)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Введите короткое название шаблона:", reply_markup=cancel_fsm_kb())


@router.message(TemplateCreate.title, F.text)
async def msg_template_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip()
    if not title or len(title) > 255:
        await message.answer("Название не должно быть пустым и длиннее 255 символов.")
        return
    await state.update_data(title=title)
    await state.set_state(TemplateCreate.content)
    await message.answer(
        "Пришлите сообщение, которое нужно сохранить: текст, фото, видео или файл.\n"
        "Его потом можно будет выбрать для рассылки.",
        reply_markup=cancel_fsm_kb(),
    )


@router.message(TemplateCreate.title)
async def msg_template_title_wrong(message: Message) -> None:
    await message.answer("Пришлите название текстом.")


@router.message(TemplateCreate.content)
async def msg_template_content(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    title = data["title"]
    text = extract_text(message)
    if not text and not any(
        [message.photo, message.video, message.document, message.animation, message.audio, message.voice]
    ):
        await message.answer("Пришлите текст или медиа.")
        return
    async with SessionLocal() as session:
        template = await repo.create_template(session, title, text, None, None)
        media_path, media_type = await save_media(message, template.id)
        if media_path:
            template.media_path = media_path
            template.media_type = media_type
            await session.commit()
            await session.refresh(template)
    await state.clear()
    await message.answer(f"Шаблон «{title}» сохранён.")
    await show_template(message, template.id)


async def show_template(message: Message, template_id: int) -> None:
    async with SessionLocal() as session:
        template = await repo.get_template(session, template_id)
    if not template:
        await message.answer("Шаблон не найден")
        return
    caption = f"<b>{escape(template.title)}</b>"
    if template.text:
        body = template.text if len(template.text) < 3500 else template.text[:3500] + "…"
        caption += f"\n\n{body}"
    kb = template_view_kb(template.id)
    if template.media_path and Path(template.media_path).exists():
        file = FSInputFile(template.media_path)
        media_type = template.media_type
        send_caption = caption[:1024]
        if media_type == "photo":
            await message.answer_photo(file, caption=send_caption, parse_mode="HTML", reply_markup=kb)
        elif media_type == "video":
            await message.answer_video(file, caption=send_caption, parse_mode="HTML", reply_markup=kb)
        elif media_type == "animation":
            await message.answer_animation(file, caption=send_caption, parse_mode="HTML", reply_markup=kb)
        elif media_type == "audio":
            await message.answer_audio(file, caption=send_caption, parse_mode="HTML", reply_markup=kb)
        elif media_type == "voice":
            await message.answer_voice(file, caption=send_caption, parse_mode="HTML", reply_markup=kb)
        else:
            await message.answer_document(file, caption=send_caption, parse_mode="HTML", reply_markup=kb)
        return
    await message.answer(caption, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("tpl:view:"))
async def cb_view_template(callback: CallbackQuery) -> None:
    template_id = int(callback.data.split(":")[2])
    await callback.answer()
    if callback.message:
        await show_template(callback.message, template_id)


@router.callback_query(F.data.startswith("tpl:del:"))
async def cb_del_template(callback: CallbackQuery) -> None:
    if is_campaign_running():
        await callback.answer("Дождитесь окончания рассылки", show_alert=True)
        return
    template_id = int(callback.data.split(":")[2])
    async with SessionLocal() as session:
        template = await repo.delete_template(session, template_id)
    if template and template.media_path:
        path = Path(template.media_path)
        if path.exists():
            path.unlink(missing_ok=True)
    await callback.answer("Удалено")
    if callback.message:
        await render_templates(callback.message)
