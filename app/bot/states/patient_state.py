"""
FSM (Finite State Machine) holatlari.
"""
from aiogram.fsm.state import State, StatesGroup


class RegistrationState(StatesGroup):
    waiting_for_lang = State()
    waiting_for_contact = State()
    waiting_for_name = State()


class FamilyState(StatesGroup):
    waiting_for_name = State()
    waiting_for_relationship = State()


class BookingFamilyState(StatesGroup):
    waiting_for_name = State()


class DeleteDataState(StatesGroup):
    confirming = State()
