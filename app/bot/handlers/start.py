from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import BTN_MAIN_MENU, main_menu_kb, start_reply_kb

router = Router()

HOME_TEXT = (
    "📬 <b>Панель рассылки</b>\n\n"
    "Сообщения уходят <b>с вашего аккаунта Telegram</b>, не от бота.\n"
    "У каждого админа своя сессия — войдите в «Настройках», затем создайте группы и шаблоны."
)


async def show_home(target: Message, *, with_start_button: bool = False) -> None:
    if with_start_button:
        await target.answer(
            HOME_TEXT + "\n\n<i>Кнопка «Главное меню» закреплена внизу — нажимайте её для возврата.</i>",
            reply_markup=start_reply_kb(),
            parse_mode="HTML",
        )
    await target.answer("Выберите раздел:", reply_markup=main_menu_kb())


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await show_home(message, with_start_button=True)


@router.message(F.text == BTN_MAIN_MENU)
async def btn_main_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await show_home(message)


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await show_home(message)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Действие отменено.")
    await show_home(message)


@router.callback_query(F.data == "menu:home")
async def cb_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.answer(HOME_TEXT, reply_markup=main_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "fsm:cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Отменено")
    if callback.message:
        await callback.message.answer(HOME_TEXT, reply_markup=main_menu_kb(), parse_mode="HTML")
