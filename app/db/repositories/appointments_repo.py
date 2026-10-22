"""
Navbatlar, qabullar va kutish ro'yxati (appointments & waitlist) repository moduli.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
import sqlite3
import aiosqlite
from app.config import settings
import pytz

tz = pytz.timezone(settings.TIMEZONE)


def get_now_str() -> str:
    return datetime.now(tz).isoformat()


async def get_next_queue_number(
    db: aiosqlite.Connection, doctor_id: int, sana: str
) -> int:
    """Kunlik yangi talon raqamini olish (#1, #2...)."""
    async with db.execute(
        "SELECT COALESCE(MAX(talon_raqami), 0) + 1 AS next_num FROM appointments WHERE doctor_id = ? AND sana = ?;",
        (doctor_id, sana)
    ) as cursor:
        row = await cursor.fetchone()
        return row["next_num"] if row else 1


async def check_user_active_booking(
    db: aiosqlite.Connection, user_id: int, doctor_id: int, sana: str,
    family_member_id: Optional[int] = None
) -> bool:
    """Ayni bir shaxs ayni shifokorga bugun faol navbat olganmi tekshirish.

    Shaxs `family_member_id` bo'yicha aniqlanadi (`NULL` = hisob egasining o'zi).
    Ilgari faqat `user_id`+ism bo'yicha solishtirilardi, bu esa bir xil ismli turli
    odamlarni (masalan, ikki "Ali") noto'g'ri bloklab qo'yardi. Endi aniq shaxs
    identifikatori ishlatiladi (`IS` — NULL-safe solishtirish).
    """
    async with db.execute(
        """
        SELECT id FROM appointments
        WHERE user_id = ? AND doctor_id = ? AND sana = ?
          AND family_member_id IS ?
          AND holat IN ('KUTMOQDA', 'CHAQIRILDI');
        """,
        (user_id, doctor_id, sana, family_member_id)
    ) as cursor:
        return bool(await cursor.fetchone())


async def count_user_daily_bookings(
    db: aiosqlite.Connection, user_id: int, sana: str
) -> int:
    """Bitta Telegram hisobdan bugun olingan faol navbatlar soni."""
    async with db.execute(
        """
        SELECT COUNT(id) as cnt FROM appointments
        WHERE user_id = ? AND sana = ? AND holat IN ('KUTMOQDA', 'CHAQIRILDI');
        """,
        (user_id, sana)
    ) as cursor:
        row = await cursor.fetchone()
        return row["cnt"] if row else 0


async def create_live_appointment(
    db: aiosqlite.Connection,
    doctor_id: int,
    sana: str,
    bemor_ismi: str,
    bemor_telefoni: Optional[str] = None,
    user_id: Optional[int] = None,
    family_member_id: Optional[int] = None
) -> Tuple[int, int]:
    """
    Jonli navbat taloni yaratish.
    Qaytaradi: (appointment_id, talon_raqami)
    """
    await db.execute("BEGIN IMMEDIATE;")
    try:
        talon_raqami = await get_next_queue_number(db, doctor_id, sana)
        now = get_now_str()
        
        cursor = await db.execute(
            """
            INSERT INTO appointments (
                doctor_id, sana, turi, talon_raqami, slot_vaqti,
                bemor_ismi, bemor_telefoni, user_id, family_member_id,
                holat, yaratilgan_vaqt
            ) VALUES (?, ?, 'LIVE', ?, NULL, ?, ?, ?, ?, 'KUTMOQDA', ?);
            """,
            (doctor_id, sana, talon_raqami, bemor_ismi, bemor_telefoni, user_id, family_member_id, now)
        )
        app_id = cursor.lastrowid
        await db.commit()
        return app_id, talon_raqami
    except sqlite3.IntegrityError:
        await db.rollback()
        raise ValueError("Talon raqamini berishda to'qnashuv yuz berdi. Qayta urinib ko'ring.")
    except Exception:
        await db.rollback()
        raise


async def create_slot_appointment(
    db: aiosqlite.Connection,
    doctor_id: int,
    sana: str,
    slot_vaqti: str,
    bemor_ismi: str,
    bemor_telefoni: Optional[str] = None,
    user_id: Optional[int] = None,
    family_member_id: Optional[int] = None
) -> Tuple[int, int]:
    """
    Oldindan slot band qilish.
    """
    await db.execute("BEGIN IMMEDIATE;")
    try:
        # Slot band qilinganmi tekshirish
        async with db.execute(
            """
            SELECT id FROM appointments
            WHERE doctor_id = ? AND sana = ? AND slot_vaqti = ?
              AND holat IN ('KUTMOQDA', 'CHAQIRILDI', 'YAKUNLANDI');
            """,
            (doctor_id, sana, slot_vaqti)
        ) as cur:
            if await cur.fetchone():
                raise ValueError("Bu slot allaqachon band qilingan!")

        talon_raqami = await get_next_queue_number(db, doctor_id, sana)
        now = get_now_str()

        cursor = await db.execute(
            """
            INSERT INTO appointments (
                doctor_id, sana, turi, talon_raqami, slot_vaqti,
                bemor_ismi, bemor_telefoni, user_id, family_member_id,
                holat, yaratilgan_vaqt
            ) VALUES (?, ?, 'SLOT', ?, ?, ?, ?, ?, ?, 'KUTMOQDA', ?);
            """,
            (doctor_id, sana, talon_raqami, slot_vaqti, bemor_ismi, bemor_telefoni, user_id, family_member_id, now)
        )
        app_id = cursor.lastrowid
        await db.commit()
        return app_id, talon_raqami
    except sqlite3.IntegrityError:
        await db.rollback()
        raise ValueError("Bu slot allaqachon band qilingan!")
    except Exception:
        await db.rollback()
        raise


async def get_appointment_by_id(
    db: aiosqlite.Connection, appointment_id: int
) -> Optional[Dict[str, Any]]:
    query = """
        SELECT a.*, d.ism_uz as doctor_ism_uz, d.ism_ru as doctor_ism_ru,
               d.xona as doctor_xona, d.ortacha_vaqt as doctor_ortacha_vaqt,
               s.nomi_uz as mutaxassislik_uz, s.nomi_ru as mutaxassislik_ru,
               u.telegram_id as user_tg_id, u.til as user_lang
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        LEFT JOIN specialties s ON d.specialty_id = s.id
        LEFT JOIN users u ON a.user_id = u.id
        WHERE a.id = ?;
    """
    async with db.execute(query, (appointment_id,)) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_user_active_appointments(
    db: aiosqlite.Connection, user_id: int
) -> List[Dict[str, Any]]:
    """Foydalanuvchining faol navbatlari (KUTMOQDA yoki CHAQIRILDI)."""
    query = """
        SELECT a.*, d.ism_uz as doctor_ism_uz, d.ism_ru as doctor_ism_ru,
               d.xona as doctor_xona, d.ortacha_vaqt as doctor_ortacha_vaqt,
               s.nomi_uz as mutaxassislik_uz, s.nomi_ru as mutaxassislik_ru
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        LEFT JOIN specialties s ON d.specialty_id = s.id
        WHERE a.user_id = ? AND a.holat IN ('KUTMOQDA', 'CHAQIRILDI')
        ORDER BY a.sana ASC, a.talon_raqami ASC;
    """
    async with db.execute(query, (user_id,)) as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_today_queue_for_doctor(
    db: aiosqlite.Connection, doctor_id: int, sana: str
) -> List[Dict[str, Any]]:
    """Shifokorning bugungi navbatidagi barcha yozuvlar.

    Tartib PROJECT_PLAN §3.5 ga mos: jonli qabul tugashigacha (slot boshlanishiga qadar)
    jonli navbat bemorlari oldinda turadi; slot vaqti kelgach, vaqti kelgan slot
    bemorlari birinchi o'ringa chiqadi, qolganlar orqasida qoladi.
    """
    now_dt = datetime.now(tz)
    now_hhmm = now_dt.strftime("%H:%M")
    today_str = now_dt.strftime("%Y-%m-%d")

    try:
        weekday = datetime.strptime(sana, "%Y-%m-%d").weekday()
    except ValueError:
        weekday = now_dt.weekday()

    async with db.execute(
        "SELECT slot_boshlanish FROM schedules WHERE doctor_id = ? AND hafta_kuni = ? AND faol = 1;",
        (doctor_id, weekday)
    ) as cur:
        sched_row = await cur.fetchone()
    slot_start = (sched_row["slot_boshlanish"] if sched_row else None) or settings.SLOT_START_TIME

    # Bugungi kun uchun, slot vaqti boshlangandan keyin slot bemorlari oldinga chiqadi
    prefer_slots = 1 if (sana == today_str and now_hhmm >= slot_start) else 0

    query = """
        SELECT a.*, u.telegram_id as user_tg_id, u.til as user_lang, u.id as user_id
        FROM appointments a
        LEFT JOIN users u ON a.user_id = u.id
        WHERE a.doctor_id = ? AND a.sana = ?
        ORDER BY
            CASE
                WHEN ? = 1 AND a.turi = 'SLOT' AND a.slot_vaqti IS NOT NULL AND a.slot_vaqti <= ? THEN 0
                WHEN a.turi = 'LIVE' THEN 1
                ELSE 2
            END ASC,
            CASE WHEN a.turi = 'SLOT' THEN a.slot_vaqti ELSE '99:99' END ASC,
            a.talon_raqami ASC;
    """
    async with db.execute(query, (doctor_id, sana, prefer_slots, now_hhmm)) as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def count_waiting_before(
    db: aiosqlite.Connection, doctor_id: int, sana: str, talon_raqami: int,
    turi: Optional[str] = None
) -> int:
    """Belgilangan talondan oldinda kutayotgan faol odamlar soni.

    `turi` berilsa faqat shu turdagi (masalan, 'LIVE') navbatlar sanaladi. Bu jonli
    navbat ETA sini to'g'ri hisoblash uchun muhim: 15:00 dagi slot bemorlari jonli
    navbatda oldinda turmaydi, shuning uchun ular ETA ni oshirib yubormasligi kerak.
    """
    query = """
        SELECT COUNT(id) as cnt FROM appointments
        WHERE doctor_id = ? AND sana = ? AND talon_raqami < ?
          AND holat IN ('KUTMOQDA', 'CHAQIRILDI')
    """
    params = [doctor_id, sana, talon_raqami]
    if turi:
        query += " AND turi = ?"
        params.append(turi)

    async with db.execute(query, tuple(params)) as cursor:
        row = await cursor.fetchone()
        return row["cnt"] if row else 0


async def set_appointment_status(
    db: aiosqlite.Connection, appointment_id: int, holat: str
) -> bool:
    now = get_now_str()
    # CHAQIRILDI -> called_at yoziladi; KUTMOQDA (qaytarish) -> called_at tozalanadi,
    # aks holda "qaytarilgan" bemor statistikada chaqirilgan deb hisoblanardi.
    if holat == "CHAQIRILDI":
        called_at_clause = ", called_at = ?"
    elif holat == "KUTMOQDA":
        called_at_clause = ", called_at = NULL"
    else:
        called_at_clause = ""
    finished_at_clause = ", finished_at = ?" if holat == "YAKUNLANDI" else ""

    query = f"UPDATE appointments SET holat = ?{called_at_clause}{finished_at_clause} WHERE id = ?;"
    params = [holat]
    if holat == "CHAQIRILDI":
        params.append(now)
    elif holat == "YAKUNLANDI":
        params.append(now)
    params.append(appointment_id)

    await db.execute(query, tuple(params))
    await db.commit()
    return True


async def check_in_appointment(db: aiosqlite.Connection, appointment_id: int) -> bool:
    """Bemor klinikaga yetib kelganini belgilash."""
    now = get_now_str()
    await db.execute(
        "UPDATE appointments SET checked_in_at = ? WHERE id = ?;", (now, appointment_id)
    )
    await db.commit()
    return True


async def cancel_appointment(db: aiosqlite.Connection, appointment_id: int) -> bool:
    """Navbatni bekor qilish (faol holatlardan). Qaytaradi: muvaffaqiyatli o'zgargan bo'lsa True."""
    cursor = await db.execute(
        """
        UPDATE appointments SET holat = 'BEKOR'
        WHERE id = ? AND holat IN ('KUTMOQDA', 'CHAQIRILDI', 'OTKAZILDI');
        """,
        (appointment_id,)
    )
    await db.commit()
    return cursor.rowcount > 0


async def expire_day_appointments(db: aiosqlite.Connection, sana: str) -> int:
    """Kun oxirida qabul qilinmagan navbatlarni EXPIRED qilish."""
    cursor = await db.execute(
        """
        UPDATE appointments SET holat = 'MUDDATI_OTDI'
        WHERE sana = ? AND holat IN ('KUTMOQDA', 'CHAQIRILDI');
        """,
        (sana,)
    )
    await db.commit()
    return cursor.rowcount


async def confirm_appointment(db: aiosqlite.Connection, appointment_id: int) -> bool:
    """Eslatma orqali navbatni tasdiqlash (faqat hali kutayotgan bo'lsa).

    Tasdiqlash vaqti `tasdiqlangan_at` ustuniga yoziladi (ilgari bu amal amalda
    hech narsa qilmasdi — holat KUTMOQDA dan KUTMOQDA ga o'zgartirilardi).
    """
    now = get_now_str()
    cursor = await db.execute(
        "UPDATE appointments SET tasdiqlangan_at = ? WHERE id = ? AND holat = 'KUTMOQDA';",
        (now, appointment_id)
    )
    await db.commit()
    return cursor.rowcount > 0


async def mark_one_hour_reminder_sent(
    db: aiosqlite.Connection, appointment_id: int
) -> None:
    """'1 soatdan keyin' eslatmasi yuborilganini belgilash (takroriy yuborishdan himoya)."""
    now = get_now_str()
    await db.execute(
        "UPDATE appointments SET eslatma_1soat_at = ? WHERE id = ?;",
        (now, appointment_id)
    )
    await db.commit()


async def cancel_appointments_for_date(
    db: aiosqlite.Connection, doctor_id: Optional[int], sana: str
) -> List[Dict[str, Any]]:
    """Shifokor (yoki butun klinika) uchun belgilangan kungi faol navbatlarni bekor qilish va ro'yxatni qaytarish."""
    query = """
        SELECT a.*, u.telegram_id as user_tg_id, u.til as user_lang, d.ism_uz as doctor_name_uz, d.ism_ru as doctor_name_ru
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        LEFT JOIN users u ON a.user_id = u.id
        WHERE a.sana = ? AND a.holat IN ('KUTMOQDA', 'CHAQIRILDI')
    """
    params = [sana]
    if doctor_id:
        query += " AND a.doctor_id = ?"
        params.append(doctor_id)

    async with db.execute(query, tuple(params)) as cur:
        rows = await cur.fetchall()
        apps = [dict(r) for r in rows]

    update_query = "UPDATE appointments SET holat = 'BEKOR' WHERE sana = ? AND holat IN ('KUTMOQDA', 'CHAQIRILDI')"
    update_params = [sana]
    if doctor_id:
        update_query += " AND doctor_id = ?"
        update_params.append(doctor_id)

    await db.execute(update_query, tuple(update_params))
    await db.commit()
    return apps


async def add_to_waitlist(
    db: aiosqlite.Connection, doctor_id: int, sana: str, user_id: int, bemor_ismi: str
) -> int:
    """Bo'shagan slotlar uchun kutish ro'yxatiga yozilish (takroriy yozuvlarning oldini oladi)."""
    # Allaqachon kutayotganmi?
    async with db.execute(
        """
        SELECT id FROM waitlist
        WHERE doctor_id = ? AND sana = ? AND user_id = ? AND holat = 'KUTMOQDA'
        LIMIT 1;
        """,
        (doctor_id, sana, user_id)
    ) as cur:
        existing = await cur.fetchone()
    if existing:
        return existing["id"]

    async with db.execute(
        "SELECT COALESCE(MAX(tartib), 0) + 1 as next_order FROM waitlist WHERE doctor_id = ? AND sana = ?;",
        (doctor_id, sana)
    ) as cur:
        row = await cur.fetchone()
        order = row["next_order"] if row else 1

    cursor = await db.execute(
        """
        INSERT INTO waitlist (doctor_id, sana, user_id, bemor_ismi, tartib, holat)
        VALUES (?, ?, ?, ?, ?, 'KUTMOQDA');
        """,
        (doctor_id, sana, user_id, bemor_ismi, order)
    )
    await db.commit()
    return cursor.lastrowid


async def get_next_waitlist_candidate(
    db: aiosqlite.Connection, doctor_id: int, sana: str
) -> Optional[Dict[str, Any]]:
    """Kutish ro'yxatidagi birinchi kutayotgan nomzodni olish."""
    query = """
        SELECT w.*, u.telegram_id as user_tg_id, u.til as user_lang,
               d.ism_uz as doctor_name_uz, d.ism_ru as doctor_name_ru
        FROM waitlist w
        JOIN users u ON w.user_id = u.id
        JOIN doctors d ON w.doctor_id = d.id
        WHERE w.doctor_id = ? AND w.sana = ? AND w.holat = 'KUTMOQDA'
        ORDER BY w.tartib ASC LIMIT 1;
    """
    async with db.execute(query, (doctor_id, sana)) as cur:
        row = await cur.fetchone()
        return dict(row) if row else None


async def set_waitlist_status(
    db: aiosqlite.Connection, waitlist_id: int, holat: str,
    slot_vaqti: Optional[str] = None
) -> bool:
    """Kutish ro'yxatidagi nomzod holatini yangilash.

    `slot_vaqti` berilsa, taklif qilingan slot vaqti ham saqlanadi (muddat tugagach
    keyingi nomzodga o'sha slotni qayta taklif qilish uchun zarur).
    """
    now = get_now_str()
    if slot_vaqti is not None:
        await db.execute(
            "UPDATE waitlist SET holat = ?, taklif_yuborilgan_vaqt = ?, taklif_slot_vaqti = ? WHERE id = ?;",
            (holat, now, slot_vaqti, waitlist_id)
        )
    else:
        await db.execute(
            "UPDATE waitlist SET holat = ?, taklif_yuborilgan_vaqt = ? WHERE id = ?;",
            (holat, now, waitlist_id)
        )
    await db.commit()
    return True


async def is_slot_occupied(
    db: aiosqlite.Connection, doctor_id: int, sana: str, slot_vaqti: str
) -> bool:
    """Slot haqiqatan bandmi (faol holatlarda) tekshirish."""
    async with db.execute(
        """
        SELECT id FROM appointments
        WHERE doctor_id = ? AND sana = ? AND slot_vaqti = ?
          AND holat IN ('KUTMOQDA', 'CHAQIRILDI', 'YAKUNLANDI')
        LIMIT 1;
        """,
        (doctor_id, sana, slot_vaqti)
    ) as cur:
        return (await cur.fetchone()) is not None


async def expire_stale_waitlist_offers(
    db: aiosqlite.Connection, older_than_iso: str
) -> List[Dict[str, Any]]:
    """Muddati o'tgan TAKLIF_YUBORILDI yozuvlarni MUDDATI_OTDI qilish.

    Qaytaradi: muddati o'tgan yozuvlar ro'yxati (doctor_id, sana, taklif_slot_vaqti) —
    bo'shagan slotni keyingi nomzodga taklif qilish uchun.
    """
    async with db.execute(
        """
        SELECT id, doctor_id, sana, taklif_slot_vaqti FROM waitlist
        WHERE holat = 'TAKLIF_YUBORILDI'
          AND taklif_yuborilgan_vaqt IS NOT NULL
          AND taklif_yuborilgan_vaqt < ?;
        """,
        (older_than_iso,)
    ) as cur:
        rows = await cur.fetchall()

    expired = [dict(r) for r in rows]
    for r in expired:
        await db.execute(
            "UPDATE waitlist SET holat = 'MUDDATI_OTDI' WHERE id = ?;", (r["id"],)
        )
    if expired:
        await db.commit()
    return expired


async def mark_waitlist_accepted(
    db: aiosqlite.Connection, user_id: int, doctor_id: int, sana: str
) -> int:
    """Bemor slotni band qilganda uning kutish ro'yxati yozuvini QABUL_QILINDI qilish."""
    cursor = await db.execute(
        """
        UPDATE waitlist SET holat = 'QABUL_QILINDI'
        WHERE user_id = ? AND doctor_id = ? AND sana = ?
          AND holat IN ('TAKLIF_YUBORILDI', 'KUTMOQDA');
        """,
        (user_id, doctor_id, sana)
    )
    await db.commit()
    return cursor.rowcount
