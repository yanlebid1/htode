from aiogram.dispatcher.filters.state import StatesGroup, State

class SupportStates(StatesGroup):
    waiting_for_category = State()
