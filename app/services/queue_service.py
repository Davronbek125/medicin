"""
Klinika Navbat Tizimi - Navbat mantiqi va Taxminiy vaqtni (ETA) hisoblash xizmati.
"""
from datetime import datetime, timedelta, time
from typing import Tuple
import aiosqlite
import pytz
from app.config import settings
from app.db.repositories import appointments_repo, doctors_repo

tz = pytz.timezone(settings.TIMEZONE)


def get_current_datetime() -> datetime:
    return datetime.now(tz)


def get_today_str() -> str:
    return get_current_datetime().strftime("%Y-%m-%d")


def parse_time_str(time_str: str) -> time:
    parts = time_str.split(":")
    return time(int(parts[0]), int(parts[1]))


async def get_doctor_learned_avg_duration(
    db: aiosqlite.Connection, doctor_id: int, fallback: int = 15
) -> int:
    """
    Shifokorning so'nggi 30 ta qabulidan haqiqiy o'rtacha davomiylikni o'rganish (Machine-learning-like smoothing).
    Agar qabullar 5 tadan kam bo'lsa, belgilangan standart vaqtdan foydalaniladi.
    """
    query = """
        SELECT called_at, finished_at
        FROM appointments
        WHERE doctor_id = ? AND holat = 'YAKUNLANDI'
          AND called_at IS NOT NULL AND finished_at IS NOT NULL
        ORDER BY id DESC LIMIT 30;
    """
    async with db.execute(query, (doctor_id,)) as cursor:
        rows = await cursor.fetchall()
        if len(rows) < 5:
            return fallback

        durations = []
        for r in rows:
            try:
                t1 = datetime.fromisoformat(r["called_at"])
                t2 = datetime.fromisoformat(r["finished_at"])
                mins = (t2 - t1).total_seconds() / 60.0
                if 3 <= mins <= 60:  # 3 daqiqadan kam yoki 60 dan ko'p bo'lgan anomaliyalarni chiqarib tashlash
                    durations.append(mins)
            except Exception:
                continue

        if durations:
            learned = round(sum(durations) / len(durations))
            return max(5, min(learned, 45))
        return fallback


async def calculate_live_queue_eta(
    db: aiosqlite.Connection, doctor_id: int, sana: str, talon_raqami: int
) -> Tuple[int, str]:
    """
    Jonli navbat uchun oldindagi odamlar soni va taxminiy kelish vaqtini hisoblash.
    Qaytaradi: (ahead_count, eta_str)
    """
    doctor = await doctors_repo.get_doctor_by_id(db, doctor_id)
    if not doctor:
        return 0, "--:--"

    # O'rtacha qabul vaqti
    avg_mins = await get_doctor_learned_avg_duration(
        db, doctor_id, fallback=(doctor.get("ortacha_vaqt") or 15)
    )

    # Oldinda kutayotganlar soni (faqat jonli navbatdagilar — slot bemorlari jonli ETA ga kirmaydi)
    ahead_count = await appointments_repo.count_waiting_before(
        db, doctor_id, sana, talon_raqami, turi="LIVE"
    )

    # Qabul boshlanish vaqti
    schedules = await doctors_repo.get_doctor_schedules(db, doctor_id)
    now_dt = get_current_datetime()
    weekday = now_dt.weekday()

    today_schedule = next((s for s in schedules if s["hafta_kuni"] == weekday), None)
    live_start = parse_time_str(today_schedule["jonli_boshlanish"] if today_schedule else "10:00")

    # Hisob boshlanish nuqtasi
    start_dt = datetime.combine(now_dt.date(), live_start)
    start_dt = tz.localize(start_dt)
    
    calc_base_dt = max(now_dt, start_dt)
    eta_start_dt = calc_base_dt + timedelta(minutes=ahead_count * avg_mins)
    eta_end_dt = eta_start_dt + timedelta(minutes=avg_mins)

    eta_str = f"~{eta_start_dt.strftime('%H:%M')} – {eta_end_dt.strftime('%H:%M')}"
    return ahead_count, eta_str


async def check_live_queue_availability(
    db: aiosqlite.Connection, doctor_id: int
) -> Tuple[bool, str]:
    """
    Bugungi kunda jonli navbat olish mumkinligini tekshirish (15:00 chegarasi va ish grafigi bilan).
    Qaytaradi: (can_book, reason_key)
    """
    now_dt = get_current_datetime()
    today_str = get_today_str()
    
    # 1. Dam olish kuni yoki ta'tilmi?
    if await doctors_repo.is_doctor_off_on_date(db, doctor_id, today_str):
        return False, "doctor_card_no_reception"

    # 2. Bugun ish kunimi?
    weekday = now_dt.weekday()
    schedules = await doctors_repo.get_doctor_schedules(db, doctor_id)
    today_schedule = next((s for s in schedules if s["hafta_kuni"] == weekday), None)
    if not today_schedule:
        return False, "doctor_card_no_reception"

    # 3. Vaqt chegaralari tekshiruvi (Standart: 08:00 dan 14:30 gacha ochiladi)
    now_time = now_dt.time()
    open_time = parse_time_str(settings.LIVE_QUEUE_OPEN_TIME)
    cutoff_time = parse_time_str(settings.LIVE_QUEUE_CUTOFF_TIME)
    
    if now_time < open_time:
        return False, "live_queue_not_started"
    if now_time >= cutoff_time:
        return False, "live_queue_closed_msg"

    # 4. Hisoblangan taxminiy vaqt 15:00 dan oshib ketadimi?
    doctor = await doctors_repo.get_doctor_by_id(db, doctor_id)
    if not doctor:
        return False, "doctor_card_no_reception"

    avg_mins = await get_doctor_learned_avg_duration(
        db, doctor_id, fallback=(doctor.get("ortacha_vaqt") or 15)
    )

    # Navbatdagi yangi kishi uchun oldinda qancha JONLI kutuvchi bor.
    # Slot bemorlari (15:00 dan keyin) jonli navbat sig'imiga kirmaydi — aks holda
    # slotlar ko'p bo'lgan kunda jonli navbat noto'g'ri "to'la" deb hisoblanardi.
    current_waiting = await appointments_repo.count_waiting_before(
        db, doctor_id, today_str, 10 ** 9, turi="LIVE"
    )

    live_start = parse_time_str(today_schedule["jonli_boshlanish"])
    live_end = parse_time_str(today_schedule["jonli_tugash"])

    start_dt = datetime.combine(now_dt.date(), live_start)
    start_dt = tz.localize(start_dt)
    calc_base_dt = max(now_dt, start_dt)

    next_patient_eta = calc_base_dt + timedelta(minutes=current_waiting * avg_mins)
    limit_dt = tz.localize(datetime.combine(now_dt.date(), live_end))

    if next_patient_eta >= limit_dt:
        return False, "doctor_card_live_full"

    return True, "ok"
