"""
Klinika Navbat Tizimi - Oldindan yozilish (Slotlar) va Kutish ro'yxati xizmati.
"""
from datetime import datetime, timedelta, time
from typing import List, Dict, Any
import aiosqlite
import pytz
from app.config import settings
from app.db.connection import get_db
from app.db.repositories import doctors_repo, appointments_repo

tz = pytz.timezone(settings.TIMEZONE)

HAFTA_KUNLARI_UZ = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
HAFTA_KUNLARI_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


async def get_available_booking_dates(
    db: aiosqlite.Connection, doctor_id: int, days_ahead: int = 7
) -> List[Dict[str, Any]]:
    """
    Shifokorga oldindan yozilish mumkin bo'lgan kunlar ro'yxatini shakllantirish.
    Dam olish kunlari va ta'tillar avtomatik chiqarib tashlanadi.
    """
    now_dt = datetime.now(tz)
    schedules = await doctors_repo.get_doctor_schedules(db, doctor_id)
    working_weekdays = {s["hafta_kuni"] for s in schedules}

    available_dates = []

    for i in range(days_ahead):
        target_dt = now_dt + timedelta(days=i)
        target_sana = target_dt.strftime("%Y-%m-%d")
        weekday = target_dt.weekday()

        # 1. Shifokorning ish kunimi?
        if weekday not in working_weekdays:
            continue

        # 2. Dam olish kuni yoki ta'til e'lon qilinganmi?
        if await doctors_repo.is_doctor_off_on_date(db, doctor_id, target_sana):
            continue

        # 3. Agar bugungi kun bo'lsa va slot vaqti (16:00) o'tib ketgan bo'lsa, bugunni chiqarmaslik
        if i == 0:
            schedule = next((s for s in schedules if s["hafta_kuni"] == weekday), None)
            slot_end_str = schedule["slot_tugash"] if schedule else "16:00"
            parts = slot_end_str.split(":")
            if now_dt.time() >= time(int(parts[0]), int(parts[1])):
                continue

        available_dates.append({
            "sana": target_sana,
            "kun_nomi_uz": f"{HAFTA_KUNLARI_UZ[weekday]} ({target_dt.strftime('%d.%m')})",
            "kun_nomi_ru": f"{HAFTA_KUNLARI_RU[weekday]} ({target_dt.strftime('%d.%m')})"
        })

    return available_dates


async def get_available_slots_for_date(
    db: aiosqlite.Connection, doctor_id: int, sana: str
) -> List[Dict[str, Any]]:
    """
    Tanlangan sana uchun bo'sh slotlar ro'yxatini shakllantirish.
    Slot uzunligi shifokorning ortacha_vaqt qiymatiga teng.
    """
    doctor = await doctors_repo.get_doctor_by_id(db, doctor_id)
    if not doctor:
        return []

    target_dt = datetime.strptime(sana, "%Y-%m-%d").date()
    weekday = target_dt.weekday()

    schedules = await doctors_repo.get_doctor_schedules(db, doctor_id)
    schedule = next((s for s in schedules if s["hafta_kuni"] == weekday), None)
    if not schedule:
        return []

    # Slotlar oralig'i (masalan 15:00 dan 16:00 gacha)
    slot_start_str = schedule.get("slot_boshlanish", "15:00")
    slot_end_str = schedule.get("slot_tugash", "16:00")
    # `ortacha_vaqt` ustuni NULL bo'lishi mumkin (sxemada NOT NULL emas), `max(10, None)`
    # xato bergan bo'lardi — shuning uchun ehtiyotkor zaxira qiymat ishlatamiz.
    slot_mins = max(10, doctor.get("ortacha_vaqt") or 15)

    start_h, start_m = map(int, slot_start_str.split(":"))
    end_h, end_m = map(int, slot_end_str.split(":"))

    current_slot_dt = datetime.combine(target_dt, time(start_h, start_m))
    end_slot_dt = datetime.combine(target_dt, time(end_h, end_m))

    # Allaqachon band qilingan slotlar
    async with db.execute(
        """
        SELECT slot_vaqti FROM appointments
        WHERE doctor_id = ? AND sana = ? AND slot_vaqti IS NOT NULL
          AND holat IN ('KUTMOQDA', 'CHAQIRILDI', 'YAKUNLANDI');
        """,
        (doctor_id, sana)
    ) as cur:
        booked_rows = await cur.fetchall()
        booked_slots = {r["slot_vaqti"] for r in booked_rows}

    slots = []
    now_dt = datetime.now(tz)
    is_today = (target_dt == now_dt.date())

    while current_slot_dt < end_slot_dt:
        time_str = current_slot_dt.strftime("%H:%M")
        
        # Bugun bo'lsa va o'tib ketgan vaqt bo'lsa, band deb ko'rsatiladi
        is_past = is_today and (current_slot_dt.time() <= now_dt.time())
        is_available = (time_str not in booked_slots) and not is_past

        slots.append({
            "vaqt": time_str,
            "mavjud": is_available
        })
        current_slot_dt += timedelta(minutes=slot_mins)

    return slots


async def offer_freed_slot(
    bot, doctor_id: int, sana: str, slot_vaqti: str
) -> bool:
    """Bo'shagan slotni kutish ro'yxatidagi navbatdagi nomzodga taklif qilish.

    Slot hali ham bo'sh bo'lishi shart (kimdir allaqachon band qilgan bo'lsa — taklif qilinmaydi).
    Nomzod belgilangan muddatda qabul qilmasa, `expire_stale_waitlist_offers` orqali
    keyingi nomzodga o'tkaziladi. Qaytaradi: taklif yuborilgan bo'lsa True.
    """
    if not slot_vaqti:
        return False

    # Tsikl importining oldini olish uchun funksiya ichida import qilinadi
    from app.services import notification

    async with get_db() as db:
        if await appointments_repo.is_slot_occupied(db, doctor_id, sana, slot_vaqti):
            return False
        candidate = await appointments_repo.get_next_waitlist_candidate(db, doctor_id, sana)
        if not candidate:
            return False
        await appointments_repo.set_waitlist_status(
            db, candidate["id"], "TAKLIF_YUBORILDI", slot_vaqti=slot_vaqti
        )

    if bot and candidate.get("user_tg_id"):
        c_lang = candidate.get("user_lang") or "uz"
        doc_name = candidate.get(f"doctor_name_{c_lang}") or candidate.get("doctor_name_uz")
        await notification.notify_waitlist_slot_available(
            bot, candidate["user_tg_id"], doctor_id, doc_name, sana, slot_vaqti, c_lang
        )
    return True
