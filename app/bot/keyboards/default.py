"""
Telegram Bot - Default (Reply) klaviaturalar.
"""
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from app.services.i18n import t


def get_contact_keyboard(lang: str = "uz") -> ReplyKeyboardMarkup:
    """Telefon raqamni ulashish klaviaturasi."""
    btn = KeyboardButton(text=t("btn_share_contact", lang), request_contact=True)
    return ReplyKeyboardMarkup(
        keyboard=[[btn]],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def get_main_menu_keyboard(lang: str = "uz", is_staff: bool = False, webapp_url: str = "") -> ReplyKeyboardMarkup:
    """Asosiy menyu klaviaturasi."""
    keyboard = [
        [
            KeyboardButton(text=t("menu_doctors", lang)),
            KeyboardButton(text=t("menu_my_queue", lang))
        ],
        [
            KeyboardButton(text=t("menu_family", lang)),
            KeyboardButton(text=t("menu_about", lang))
        ],
        [
            KeyboardButton(text=t("menu_contact", lang)),
            KeyboardButton(text=t("menu_lang", lang))
        ],
        [
            KeyboardButton(text=t("menu_delete_data", lang))
        ]
    ]

    # Agar xodim bo'lsa yoki WebApp ochish kerak bo'lsa
    if is_staff and webapp_url:
        from aiogram.types import WebAppInfo
        keyboard.insert(0, [
            KeyboardButton(text="💼 Boshqaruv paneli (WebApp)", web_app=WebAppInfo(url=webapp_url))
        ])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )
