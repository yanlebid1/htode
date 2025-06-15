# services/telegram_service/app/states/advances_states.py

from aiogram.dispatcher.filters.state import State, StatesGroup

class AdvancedFilterStates(StatesGroup):
    waiting_for_floor_max = State()
    waiting_for_first_floor = State()
    waiting_for_last_floor = State()
    waiting_for_pets_allowed = State()
    waiting_for_without_broker = State()
    waiting_for_advanced_confirmation = State()
