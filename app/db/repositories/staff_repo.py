"""
Xodimlar, taklif havolalari va audit jurnali repository moduli.
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import secrets
import aiosqlite
from app.config import settings
import pytz

tz = pytz.timezone(settings.TIMEZONE)


def get_now_str() -> str:
    return datetime.now(tz).isoformat()


async def get_staff_by_telegram_id(
    db: aiosqlite.Connection, telegram_id: int
) -> Optional[Dict[str, Any]]:
    query = """
        SELECT s.*, d.ism_uz as doctor_name
        FROM staff s
        LEFT JOIN doctors d ON s.doctor_id = d.id
        WHERE s.telegram_id = ? AND s.faol = 1;
    """
    async with db.execute(query, (telegram_id,)) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None


async def list_all_staff(db: aiosqlite.Connection) -> List[Dict[str, Any]]:
    query = """
        SELECT s.*, d.ism_uz as doctor_name
        FROM staff s
        LEFT JOIN doctors d ON s.doctor_id = d.id
        ORDER BY s.id DESC;
    """
    async with db.execute(query) as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_staff_by_id(
    db: aiosqlite.Connection, staff_id: int
) -> Optional[Dict[str, Any]]:
    async with db.execute("SELECT * FROM staff WHERE id = ?;", (staff_id,)) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None


async def count_active_super_admins(db: aiosqlite.Connection) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM staff WHERE rol = 'SUPER_ADMIN' AND faol = 1;"
    ) as cursor:
        row = await cursor.fetchone()
        return int(row[0]) if row else 0


async def create_invite_token(
    db: aiosqlite.Connection, rol: str, doctor_id: Optional[int] = None, hours_valid: int = 24
) -> str:
    """Bir martalik xodim taklif havolasi tokenini yaratish."""
    token = secrets.token_urlsafe(16)
    expire_dt = datetime.now(tz) + timedelta(hours=hours_valid)
    
    await db.execute(
        """
        INSERT INTO invites (token, rol, doctor_id, amal_muddati, ishlatilgan)
        VALUES (?, ?, ?, ?, 0);
        """,
        (token, rol, doctor_id, expire_dt.isoformat())
    )
    await db.commit()
    return token


async def get_valid_invite(
    db: aiosqlite.Connection, token: str
) -> Optional[Dict[str, Any]]:
    now = get_now_str()
    async with db.execute(
        """
        SELECT * FROM invites
        WHERE token = ? AND ishlatilgan = 0 AND amal_muddati > ?;
        """,
        (token, now)
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None


async def redeem_invite(
    db: aiosqlite.Connection, token: str, telegram_id: int
) -> Optional[Dict[str, Any]]:
    """Taklif havolasini qabul qilish va xodimni ro'yxatdan o'tkazish."""
    invite = await get_valid_invite(db, token)
    if not invite:
        return None

    now = get_now_str()
    await db.execute("BEGIN IMMEDIATE;")
    try:
        # Xodim jadvaliga yozish yoki yangilash
        await db.execute(
            """
            INSERT INTO staff (telegram_id, rol, doctor_id, faol, biriktirilgan_sana)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                rol = excluded.rol,
                doctor_id = excluded.doctor_id,
                faol = 1,
                biriktirilgan_sana = excluded.biriktirilgan_sana;
            """,
            (telegram_id, invite["rol"], invite["doctor_id"], now)
        )
        
        # Tokendan foydalanildi deb belgilash
        await db.execute(
            "UPDATE invites SET ishlatilgan = 1 WHERE id = ?;", (invite["id"],)
        )
        await db.commit()
        return invite
    except Exception:
        await db.rollback()
        raise


async def revoke_staff(db: aiosqlite.Connection, staff_id: int) -> bool:
    """Xodim huquqini bekor qilish."""
    await db.execute("UPDATE staff SET faol = 0 WHERE id = ?;", (staff_id,))
    await db.commit()
    return True


async def log_audit_action(
    db: aiosqlite.Connection,
    amal: str,
    obyekt: Optional[str] = None,
    tafsilot: Optional[str] = None,
    staff_id: Optional[int] = None,
    telegram_id: Optional[int] = None
) -> None:
    now = get_now_str()
    await db.execute(
        """
        INSERT INTO audit_log (staff_id, telegram_id, amal, obyekt, tafsilot, sana_vaqt)
        VALUES (?, ?, ?, ?, ?, ?);
        """,
        (staff_id, telegram_id, amal, obyekt, tafsilot, now)
    )
    await db.commit()


async def get_recent_audit_logs(
    db: aiosqlite.Connection, limit: int = 50
) -> List[Dict[str, Any]]:
    """Xodimlar va admin amallari jurnali ro'yxatini olish."""
    async with db.execute(
        """
        SELECT id, staff_id, telegram_id, amal, obyekt, tafsilot, sana_vaqt
        FROM audit_log
        ORDER BY id DESC LIMIT ?;
        """,
        (limit,)
    ) as cur:
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
