from aiogram.fsm.state import State, StatesGroup


class UserState(StatesGroup):
    unauthorized = State()
    authorized = State()
    waiting_for_shopName = State()
    waiting_for_location = State()
    waiting_for_type_photo = State()
    waiting_for_competitor_brand = State()
    waiting_for_dmp_brand = State()
    waiting_for_competitor_count_after_brand = State()
    waiting_for_photo = State()
