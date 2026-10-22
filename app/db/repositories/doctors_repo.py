"""
Shifokorlar, mutaxassisliklar va ish grafigi bilan ishlash repository moduli.
"""
from typing import Optional, List, Dict, Any
import aiosqlite


# `update_doctor` orqali yangilanishi mumkin bo'lgan ustunlar (oq ro'yxat).
_DOCTOR_UPDATABLE_FIELDS = {
    "specialty_id", "ism_uz", "ism_ru", "xona", "rasm_url", "tajriba_yili",
    "tavsif_uz", "tavsif_ru", "ortacha_vaqt", "botda_korinadi", "tartib",
    "arxivlangan",
}


# --- Mutaxassisliklar ---
async def get_all_specialties(db: aiosqlite.Connection) -> List[Dict[str, Any]]:
    async with db.execute(
        "SELECT * FROM specialties ORDER BY tartib ASC, id ASC;"
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_specialties_with_visible_doctors(db: aiosqlite.Connection) -> List[Dict[str, Any]]:
    """Bot katalogi uchun: ko'rinadigan (botda_korinadi=1) shifokori bor mutaxassisliklar.

    Bo'sh mutaxassisliklar ro'yxatga kirmaydi — aks holda foydalanuvchi tugmani
    bosib, "faol shifokorlar mavjud emas" degan xabarni oladi va bot ishlamayotgan
    deb o'ylaydi.
    """
    async with db.execute(
        """
        SELECT s.* FROM specialties s
        WHERE EXISTS (
            SELECT 1 FROM doctors d
            WHERE d.specialty_id = s.id
              AND d.arxivlangan = 0
              AND d.botda_korinadi = 1
        )
        ORDER BY s.tartib ASC, s.id ASC;
        """
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def create_specialty(
    db: aiosqlite.Connection, nomi_uz: str, nomi_ru: str, tartib: int = 0
) -> int:
    cursor = await db.execute(
        "INSERT INTO specialties (nomi_uz, nomi_ru, tartib) VALUES (?, ?, ?);",
        (nomi_uz, nomi_ru, tartib)
    )
    await db.commit()
    return cursor.lastrowid


async def delete_specialty(db: aiosqlite.Connection, specialty_id: int) -> bool:
    await db.execute("DELETE FROM specialties WHERE id = ?;", (specialty_id,))
    await db.commit()
    return True


# --- Shifokorlar ---
async def get_doctors_by_specialty(
    db: aiosqlite.Connection, specialty_id: int, only_visible: bool = True
) -> List[Dict[str, Any]]:
    query = """
        SELECT d.*, s.nomi_uz as mutaxassislik_uz, s.nomi_ru as mutaxassislik_ru
        FROM doctors d
        LEFT JOIN specialties s ON d.specialty_id = s.id
        WHERE d.specialty_id = ? AND d.arxivlangan = 0
    """
    params = [specialty_id]
    if only_visible:
        query += " AND d.botda_korinadi = 1"
    query += " ORDER BY d.tartib ASC, d.id ASC;"
    
    async with db.execute(query, params) as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_all_doctors(
    db: aiosqlite.Connection, include_archived: bool = False
) -> List[Dict[str, Any]]:
    query = """
        SELECT d.*, s.nomi_uz as mutaxassislik_uz, s.nomi_ru as mutaxassislik_ru
        FROM doctors d
        LEFT JOIN specialties s ON d.specialty_id = s.id
    """
    if not include_archived:
        query += " WHERE d.arxivlangan = 0"
    query += " ORDER BY d.tartib ASC, d.id ASC;"
    
    async with db.execute(query) as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_doctor_by_id(
    db: aiosqlite.Connection, doctor_id: int
) -> Optional[Dict[str, Any]]:
    query = """
        SELECT d.*, s.nomi_uz as mutaxassislik_uz, s.nomi_ru as mutaxassislik_ru
        FROM doctors d
        LEFT JOIN specialties s ON d.specialty_id = s.id
        WHERE d.id = ?;
    """
    async with db.execute(query, (doctor_id,)) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None


async def create_doctor(
    db: aiosqlite.Connection,
    specialty_id: int,
    ism_uz: str,
    ism_ru: str,
    xona: str,
    tajriba_yili: int = 0,
    tavsif_uz: Optional[str] = None,
    tavsif_ru: Optional[str] = None,
    ortacha_vaqt: int = 15,
    rasm_url: Optional[str] = None,
    botda_korinadi: int = 1,
    tartib: int = 0
) -> int:
    cursor = await db.execute(
        """
        INSERT INTO doctors (
            specialty_id, ism_uz, ism_ru, xona, tajriba_yili,
            tavsif_uz, tavsif_ru, ortacha_vaqt, rasm_url,
            botda_korinadi, tartib, arxivlangan
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0);
        """,
        (
            specialty_id, ism_uz, ism_ru, xona, tajriba_yili,
            tavsif_uz, tavsif_ru, ortacha_vaqt, rasm_url,
            botda_korinadi, tartib
        )
    )
    doc_id = cursor.lastrowid
    
    # Standart grafik: Dushanba-Juma (0-4) 10:00-15:00 / 15:00-16:00
    for day in range(5):
        await db.execute(
            """
            INSERT OR IGNORE INTO schedules (doctor_id, hafta_kuni, jonli_boshlanish, jonli_tugash, slot_boshlanish, slot_tugash)
            VALUES (?, ?, '10:00', '15:00', '15:00', '16:00');
            """,
            (doc_id, day)
        )
    await db.commit()
    return doc_id


async def update_doctor(
    db: aiosqlite.Connection, doctor_id: int, **fields: Any
) -> bool:
    # Xavfsizlik: faqat oq ro'yxatdagi ustunlarni yangilaymiz (SQL injection defence-in-depth).
    fields = {k: v for k, v in fields.items() if k in _DOCTOR_UPDATABLE_FIELDS}
    if not fields:
        return False
    keys = list(fields.keys())
    set_clause = ", ".join([f"{k} = ?" for k in keys])
    values = [fields[k] for k in keys]
    values.append(doctor_id)
    
    await db.execute(
        f"UPDATE doctors SET {set_clause} WHERE id = ?;", tuple(values)
    )
    await db.commit()
    return True


async def archive_doctor(db: aiosqlite.Connection, doctor_id: int) -> bool:
    """Shifokorni arxivlash (tarix va statistika saqlanadi)."""
    await db.execute(
        "UPDATE doctors SET arxivlangan = 1, botda_korinadi = 0 WHERE id = ?;",
        (doctor_id,)
    )
    await db.commit()
    return True


# --- Ish grafigi va Dam olish kunlari ---
async def get_doctor_schedules(
    db: aiosqlite.Connection, doctor_id: int
) -> List[Dict[str, Any]]:
    async with db.execute(
        "SELECT * FROM schedules WHERE doctor_id = ? AND faol = 1 ORDER BY hafta_kuni ASC;",
        (doctor_id,)
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def update_doctor_schedule_day(
    db: aiosqlite.Connection,
    doctor_id: int,
    hafta_kuni: int,
    jonli_boshlanish: str,
    jonli_tugash: str,
    slot_boshlanish: str,
    slot_tugash: str,
    faol: int = 1
) -> None:
    await db.execute(
        """
        INSERT INTO schedules (doctor_id, hafta_kuni, jonli_boshlanish, jonli_tugash, slot_boshlanish, slot_tugash, faol)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(doctor_id, hafta_kuni) DO UPDATE SET
            jonli_boshlanish = excluded.jonli_boshlanish,
            jonli_tugash = excluded.jonli_tugash,
            slot_boshlanish = excluded.slot_boshlanish,
            slot_tugash = excluded.slot_tugash,
            faol = excluded.faol;
        """,
        (doctor_id, hafta_kuni, jonli_boshlanish, jonli_tugash, slot_boshlanish, slot_tugash, faol)
    )
    await db.commit()


async def is_doctor_off_on_date(
    db: aiosqlite.Connection, doctor_id: int, sana: str
) -> bool:
    """Belgilangan sanada shifokor yoki klinika dam olyaptimi tekshirish."""
    async with db.execute(
        """
        SELECT id FROM days_off
        WHERE sana = ? AND (doctor_id = ? OR doctor_id IS NULL)
        LIMIT 1;
        """,
        (sana, doctor_id)
    ) as cursor:
        row = await cursor.fetchone()
        return bool(row)


async def set_day_off(
    db: aiosqlite.Connection,
    sana: str,
    doctor_id: Optional[int] = None,
    sabab: Optional[str] = None
) -> int:
    # Takroriy yozuvlarning oldini olish
    if doctor_id is None:
        existing_sql = "SELECT id FROM days_off WHERE sana = ? AND doctor_id IS NULL LIMIT 1;"
        existing_params = (sana,)
    else:
        existing_sql = "SELECT id FROM days_off WHERE sana = ? AND doctor_id = ? LIMIT 1;"
        existing_params = (sana, doctor_id)

    async with db.execute(existing_sql, existing_params) as cur:
        row = await cur.fetchone()
    if row:
        await db.execute("UPDATE days_off SET sabab = ? WHERE id = ?;", (sabab, row["id"]))
        await db.commit()
        return row["id"]

    cursor = await db.execute(
        "INSERT INTO days_off (doctor_id, sana, sabab) VALUES (?, ?, ?);",
        (doctor_id, sana, sabab)
    )
    await db.commit()
    return cursor.lastrowid
