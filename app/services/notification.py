"""
Klinika Navbat Tizimi - Bemorlarga xabarnomalar yuborish xizmati.
"""
import logging
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from app.db.connection import get_db
from app.db.repositories import appointments_repo
from app.services.i18n import t

logger = logging.getLogger(__name__)


async def send_notification(
    bot: Bot, telegram_id: int, text: str, reply_markup=None
) -> bool:
    """Xavfsiz Telegram xabarini yuborish."""
    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        return True
    except TelegramForbiddenError:
        logger.warning(f"Foydalanuvchi botni bloklagan: telegram_id={telegram_id}")
        return False
    except TelegramBadRequest as e:
        logger.error(f"Xabar yuborishda xatolik: {e}")
        return False
    except Exception as e:
        logger.error(f"Kutilmagan xatolik: {e}")
        return False


async def notify_called(bot: Bot, appointment_id: int) -> bool:
    """Bemor chaqirilganda xabar berish."""
    async with get_db() as db:
        app = await appointments_repo.get_appointment_by_id(db, appointment_id)
        if not app or not app.get("user_tg_id"):
            return False

        user_tg_id = app["user_tg_id"]
        lang = app.get("user_lang") or "uz"
        doc_name = app.get(f"doctor_ism_{lang}") or app.get("doctor_ism_uz")
        room = app.get("doctor_xona")

    msg = t("notify_called", lang, room=room, doctor_name=doc_name)
    return await send_notification(bot, user_tg_id, msg)


async def notify_approaching(bot: Bot, appointment_id: int, eta_str: str) -> bool:
    """Oldida 2 kishi qolganda ogohlantirish."""
    async with get_db() as db:
        app = await appointments_repo.get_appointment_by_id(db, appointment_id)
        if not app or not app.get("user_tg_id"):
            return False

        user_tg_id = app["user_tg_id"]
        lang = app.get("user_lang") or "uz"
        room = app.get("doctor_xona")

    msg = t("notify_approaching", lang, room=room, eta=eta_str)
    return await send_notification(bot, user_tg_id, msg)


async def notify_cancelled_by_clinic(bot: Bot, appointments: list) -> int:
    """
    Shifokor qabuli bekor bo'lganda navbatdagilarga xabar berish.

    `appointments` — `cancel_appointments_for_date()` qaytargan, bekor qilishdan
    oldin olingan navbatlar ro'yxati (har birida `user_tg_id`, `user_lang`,
    `doctor_name_uz`, `doctor_name_ru` mavjud). Bu avvalgi xato tuzatildi: funksiya
    endi bazadan qayta so'ramaydi, chunki o'sha paytda navbatlar allaqachon BEKOR bo'ladi.
    """
    count = 0
    if bot is None:
        return count
    for a in appointments or []:
        if not a.get("user_tg_id"):
            continue
        lang = a.get("user_lang") or "uz"
        doc_name = a.get(f"doctor_name_{lang}") or a.get("doctor_name_uz") or "Shifokor"
        msg = t("notify_cancelled_by_clinic", lang, doctor_name=doc_name)
        if await send_notification(bot, a["user_tg_id"], msg):
            count += 1
    return count


async def notify_waitlist_slot_available(
    bot: Bot,
    user_tg_id: int,
    doctor_id: int,
    doctor_name: str,
    sana: str,
    slot_vaqti: str,
    lang: str = "uz"
) -> bool:
    """Kutish ro'yxatidagi bemorga bo'shagan slot haqida xabar berish."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    msg = t(
        "notify_waitlist_offer", lang,
        doctor_name=doctor_name,
        date=sana,
        time=slot_vaqti
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text=t("btn_book_slot", lang),
                callback_data=f"slot_{doctor_id}_{sana}_{slot_vaqti}"
            )
        ]]
    )
    return await send_notification(bot, user_tg_id, msg, reply_markup=kb)
