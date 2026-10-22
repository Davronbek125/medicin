"""
Telegram Bot - Inline klaviaturalar.
"""
from typing import List, Dict, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.services.i18n import t


def get_language_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="set_lang_uz"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang_ru")
            ]
        ]
    )


def get_specialties_keyboard(specialties: List[Dict[str, Any]], lang: str = "uz") -> InlineKeyboardMarkup:
    keyboard = []
    row = []
    for spec in specialties:
        name = spec.get(f"nomi_{lang}") or spec.get("nomi_uz")
        btn = InlineKeyboardButton(text=f"🩺 {name}", callback_data=f"spec_{spec['id']}")
        row.append(btn)
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_doctors_keyboard(doctors: List[Dict[str, Any]], lang: str = "uz") -> InlineKeyboardMarkup:
    keyboard = []
    for doc in doctors:
        name = doc.get(f"ism_{lang}") or doc.get("ism_uz")
        room = doc.get("xona")
        keyboard.append([
            InlineKeyboardButton(text=f"👨‍⚕️ {name} ({room}-xona)", callback_data=f"doc_{doc['id']}")
        ])
    
    keyboard.append([
        InlineKeyboardButton(text=t("btn_back", lang), callback_data="back_to_specs")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_doctor_card_keyboard(
    doctor_id: int, can_book_live: bool, can_book_slot: bool, lang: str = "uz"
) -> InlineKeyboardMarkup:
    keyboard = []
    if can_book_live or can_book_slot:
        keyboard.append([
            InlineKeyboardButton(text=t("btn_book", lang), callback_data=f"book_start_{doctor_id}")
        ])
    
    keyboard.append([
        InlineKeyboardButton(text=t("btn_back", lang), callback_data="back_to_doctors")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_booking_type_keyboard(
    doctor_id: int, can_book_live: bool, can_book_slot: bool, lang: str = "uz"
) -> InlineKeyboardMarkup:
    keyboard = []
    if can_book_live:
        keyboard.append([
            InlineKeyboardButton(text=t("btn_live_queue", lang), callback_data=f"btype_live_{doctor_id}")
        ])
    if can_book_slot:
        keyboard.append([
            InlineKeyboardButton(text=t("btn_slot_booking", lang), callback_data=f"btype_slot_{doctor_id}")
        ])
    
    keyboard.append([
        InlineKeyboardButton(text=t("btn_back", lang), callback_data=f"doc_{doctor_id}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_person_choice_keyboard(
    doctor_id: int,
    booking_type: str,
    extra: str,
    family_members: List[Dict[str, Any]],
    lang: str = "uz"
) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(
                text=t("btn_for_myself", lang),
                callback_data=f"person_self_{doctor_id}_{booking_type}_{extra}"
            )
        ]
    ]

    for member in family_members:
        rel = f" ({member.get('qarindoshlik')})" if member.get("qarindoshlik") else ""
        keyboard.append([
            InlineKeyboardButton(
                text=f"👤 {member['ism']}{rel}",
                callback_data=f"person_fam_{member['id']}_{doctor_id}_{booking_type}_{extra}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text=t("btn_add_family", lang),
            callback_data=f"person_addfam_{doctor_id}_{booking_type}_{extra}"
        )
    ])
    keyboard.append([
        InlineKeyboardButton(text=t("btn_back", lang), callback_data=f"doc_{doctor_id}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_dates_keyboard(doctor_id: int, dates: List[Dict[str, Any]], lang: str = "uz") -> InlineKeyboardMarkup:
    keyboard = []
    for d in dates:
        day_label = d.get(f"kun_nomi_{lang}") or d.get("kun_nomi_uz")
        keyboard.append([
            InlineKeyboardButton(
                text=f"📅 {day_label}", callback_data=f"date_{doctor_id}_{d['sana']}"
            )
        ])
    keyboard.append([
        InlineKeyboardButton(text=t("btn_back", lang), callback_data=f"doc_{doctor_id}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_slots_keyboard(doctor_id: int, sana: str, slots: List[Dict[str, Any]], lang: str = "uz") -> InlineKeyboardMarkup:
    keyboard = []
    row = []
    for s in slots:
        status_icon = "🟢" if s["mavjud"] else "🔴"
        cb = f"slot_{doctor_id}_{sana}_{s['vaqt']}" if s["mavjud"] else "slot_busy"
        btn = InlineKeyboardButton(text=f"{status_icon} {s['vaqt']}", callback_data=cb)
        row.append(btn)
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    has_available = any(s["mavjud"] for s in slots)
    if not has_available:
        keyboard.append([
            InlineKeyboardButton(
                text=t("btn_join_waitlist", lang),
                callback_data=f"waitlist_join_{doctor_id}_{sana}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(text=t("btn_back", lang), callback_data=f"btype_slot_{doctor_id}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_ticket_keyboard(appointment_id: int, is_checked_in: bool = False, lang: str = "uz") -> InlineKeyboardMarkup:
    keyboard = []
    if not is_checked_in:
        keyboard.append([
            InlineKeyboardButton(text=t("btn_check_in", lang), callback_data=f"checkin_{appointment_id}")
        ])
    keyboard.append([
        InlineKeyboardButton(text=t("btn_refresh", lang), callback_data=f"refresh_{appointment_id}"),
        InlineKeyboardButton(text=t("btn_cancel", lang), callback_data=f"cancel_{appointment_id}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_family_management_keyboard(members: List[Dict[str, Any]], lang: str = "uz") -> InlineKeyboardMarkup:
    keyboard = []
    for m in members:
        keyboard.append([
            InlineKeyboardButton(
                text=f"🗑 {m['ism']} - {t('btn_delete_family', lang)}",
                callback_data=f"delfam_{m['id']}"
            )
        ])
    keyboard.append([
        InlineKeyboardButton(text="➕ " + t("btn_add_family", lang), callback_data="add_fam_manual")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_confirm_delete_data_keyboard(lang: str = "uz") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_confirm_delete", lang), callback_data="confirm_delete_my_data")],
            [InlineKeyboardButton(text=t("btn_back", lang), callback_data="cancel_delete_data")]
        ]
    )
