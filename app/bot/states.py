from aiogram.fsm.state import State, StatesGroup


class NewSubscriptionStates(StatesGroup):
    name = State()
    origin = State()
    destination = State()
    trip_type = State()
    departure_mode = State()
    departure_dates = State()
    return_mode = State()
    return_date_mode = State()
    return_dates = State()
    duration = State()
    max_price = State()
    direct_only = State()
    confirm = State()
