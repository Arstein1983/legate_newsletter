from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

BTN_MAIN_MENU = "Главное меню"


def start_reply_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_MAIN_MENU)]],
        resize_keyboard=True,
        is_persistent=True,
    )


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Группы", callback_data="menu:groups")],
            [InlineKeyboardButton(text="✉️ Шаблоны", callback_data="menu:templates")],
            [InlineKeyboardButton(text="📣 Рассылка", callback_data="menu:broadcast")],
            [InlineKeyboardButton(text="📊 История", callback_data="menu:history")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu:settings")],
        ]
    )


def back_kb(data: str = "menu:home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data=data)]])


def groups_kb(groups: list[tuple[int, str, int]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"{name} ({count})", callback_data=f"grp:view:{gid}")] for gid, name, count in groups]
    rows.append([InlineKeyboardButton(text="➕ Создать группу", callback_data="grp:new")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def group_view_kb(group_id: int, page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить получателей", callback_data=f"grp:add:{group_id}")],
            [InlineKeyboardButton(text="📥 Импорт из файла", callback_data=f"grp:import:{group_id}")],
            [InlineKeyboardButton(text="👤 Список получателей", callback_data=f"grp:recs:{group_id}:{page}")],
            [InlineKeyboardButton(text="🗑 Удалить группу", callback_data=f"grp:del:{group_id}")],
            [InlineKeyboardButton(text="⬅️ К группам", callback_data="menu:groups")],
        ]
    )


def recipients_kb(group_id: int, items: list[tuple[int, str]], page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"🗑 {label}", callback_data=f"rec:del:{rid}:{page}")] for rid, label in items]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"grp:recs:{group_id}:{page - 1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"grp:recs:{group_id}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ К группе", callback_data=f"grp:view:{group_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_delete_group_kb(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да, удалить", callback_data=f"grp:delc:{group_id}")],
            [InlineKeyboardButton(text="Отмена", callback_data=f"grp:view:{group_id}")],
        ]
    )


def templates_kb(templates: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=title, callback_data=f"tpl:view:{tid}")] for tid, title in templates]
    rows.append([InlineKeyboardButton(text="➕ Сохранить сообщение", callback_data="tpl:new")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def template_view_kb(template_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"tpl:del:{template_id}")],
            [InlineKeyboardButton(text="⬅️ К шаблонам", callback_data="menu:templates")],
        ]
    )


def pick_groups_kb(groups: list[tuple[int, str, int]], prefix: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{name} ({count})", callback_data=f"{prefix}:{gid}")]
        for gid, name, count in groups
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pick_templates_kb(templates: list[tuple[int, str]], group_id: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=title, callback_data=f"bc:tpl:{group_id}:{tid}")] for tid, title in templates]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:broadcast")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_broadcast_kb(group_id: int, template_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Запустить", callback_data=f"bc:go:{group_id}:{template_id}")],
            [InlineKeyboardButton(text="Отмена", callback_data="menu:home")],
        ]
    )


def settings_kb(authorized: bool, running: bool) -> InlineKeyboardMarkup:
    rows = []
    if authorized:
        rows.append([InlineKeyboardButton(text="🚪 Выйти из аккаунта админа", callback_data="set:logout")])
    else:
        rows.append([InlineKeyboardButton(text="🔐 Войти в аккаунт админа", callback_data="set:login")])
    rows.append([InlineKeyboardButton(text="⏱ Пауза между сообщениями", callback_data="set:delay")])
    if running:
        rows.append([InlineKeyboardButton(text="⏹ Остановить рассылку", callback_data="set:stop")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_fsm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="fsm:cancel")]])


def done_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data="fsm:done")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="fsm:cancel")],
        ]
    )
