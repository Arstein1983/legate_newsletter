from aiogram.fsm.state import State, StatesGroup


class GroupCreate(StatesGroup):
    name = State()


class GroupAddRecipients(StatesGroup):
    waiting = State()


class GroupImport(StatesGroup):
    waiting_file = State()


class TemplateCreate(StatesGroup):
    title = State()
    content = State()


class AuthFlow(StatesGroup):
    phone = State()
    code = State()
    password = State()


class DelayChange(StatesGroup):
    value = State()
