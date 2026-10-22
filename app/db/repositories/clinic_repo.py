"""
Klinika ma'lumotlari va tahliliy hisobotlar (KPI) repository moduli.
"""
from typing import Optional, Dict, Any
import aiosqlite


# `update_clinic_info` orqali yangilanishi mumkin bo'lgan ustunlar (oq ro'yxat).
_CLINIC_UPDATABLE_FIELDS = {
    "nomi_uz", "nomi_ru", "manzil_uz", "manzil_ru",
    "lokatsiya_lat", "lokatsiya_lon", "telefonlar",
    "ish_vaqti_uz", "ish_vaqti_ru",
}


async def get_clinic_info(db: aiosqlite.Connection) -> Optional[Dict[str, Any]]:
    async with db.execute("SELECT * FROM clinic ORDER BY id ASC LIMIT 1;") as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_clinic_info(
    db: aiosqlite.Connection, **fields: Any
) -> bool:
    # Xavfsizlik: faqat oq ro'yxatdagi ustunlarni yangilaymiz (SQL injection defence-in-depth).
    fields = {k: v for k, v in fields.items() if k in _CLINIC_UPDATABLE_FIELDS}
    if not fields:
        return False
    keys = list(fields.keys())
    set_clause = ", ".join([f"{k} = ?" for k in keys])
    values = [fields[k] for k in keys]
    
    await db.execute(
        f"UPDATE clinic SET {set_clause} WHERE id = (SELECT id FROM clinic LIMIT 1);",
        tuple(values)
    )
    await db.commit()
    return True


async def get_kpi_stats(
    db: aiosqlite.Connection, sana: str
) -> Dict[str, Any]:
    """Bugungi kunlik asosiy ko'rsatkichlar (KPI)."""
    # Umumiy navbatlar statistikasi
    async with db.execute(
        """
        SELECT 
            COUNT(id) as jami_bemorlar,
            SUM(CASE WHEN holat = 'YAKUNLANDI' THEN 1 ELSE 0 END) as yakunlangan,
            SUM(CASE WHEN holat = 'KUTMOQDA' THEN 1 ELSE 0 END) as kutayotgan,
            SUM(CASE WHEN holat = 'OTKAZILDI' THEN 1 ELSE 0 END) as kelmagan,
            SUM(CASE WHEN holat = 'BEKOR' THEN 1 ELSE 0 END) as bekor_qilingan,
            SUM(CASE WHEN turi = 'LIVE' THEN 1 ELSE 0 END) as jonli_navbatlar,
            SUM(CASE WHEN turi = 'SLOT' THEN 1 ELSE 0 END) as slot_navbatlar,
            SUM(CASE WHEN user_id IS NOT NULL THEN 1 ELSE 0 END) as bot_orqali,
            SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) as reception_orqali
        FROM appointments
        WHERE sana = ?;
        """,
        (sana,)
    ) as cursor:
        stats = dict(await cursor.fetchone() or {})

    # Shifokorlar soni
    async with db.execute("SELECT COUNT(id) as cnt FROM doctors WHERE arxivlangan = 0;") as cursor:
        row = await cursor.fetchone()
        stats["faol_shifokorlar"] = row["cnt"] if row else 0

    # Kelmaslik foizi
    jami = stats.get("jami_bemorlar") or 0
    kelmagan = stats.get("kelmagan") or 0
    stats["kelmaslik_foizi"] = round((kelmagan / jami * 100), 1) if jami > 0 else 0

    # O'rtacha kutish vaqti (daqiqalarda)
    async with db.execute(
        """
        SELECT yaratilgan_vaqt, called_at
        FROM appointments
        WHERE sana = ? AND called_at IS NOT NULL;
        """,
        (sana,)
    ) as cursor:
        rows = await cursor.fetchall()
        wait_mins = []
        for r in rows:
            try:
                from datetime import datetime
                t_created = datetime.fromisoformat(r["yaratilgan_vaqt"])
                t_called = datetime.fromisoformat(r["called_at"])
                diff = (t_called - t_created).total_seconds() / 60.0
                if 0 <= diff <= 240:
                    wait_mins.append(diff)
            except Exception:
                pass
        stats["ortacha_kutish_vaqti"] = round(sum(wait_mins) / len(wait_mins)) if wait_mins else 0

    return stats
