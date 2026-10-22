"""
Foydalanuvchilar va oila a'zolari bilan ishlash repository moduli.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
import aiosqlite
from app.config import settings
import pytz

tz = pytz.timezone(settings.TIMEZONE)


def get_current_time_str() -> str:
    return datetime.now(tz).isoformat()


async def get_or_create_user(
    db: aiosqlite.Connection,
    telegram_id: int,
    ism: str,
    telefon: str,
    til: str = "uz"
) -> Dict[str, Any]:
    """Foydalanuvchini olish yoki yangi ro'yxatdan o'tkazish."""
    async with db.execute(
        "SELECT * FROM users WHERE telegram_id = ?;", (telegram_id,)
    ) as cursor:
        user = await cursor.fetchone()
        if user:
            return dict(user)

    now = get_current_time_str()
    cursor = await db.execute(
        """
        INSERT INTO users (telegram_id, ism, telefon, til, consent_at, yaratilgan_sana)
        VALUES (?, ?, ?, ?, ?, ?);
        """,
        (telegram_id, ism, telefon, til, now, now)
    )
    await db.commit()
    
    async with db.execute("SELECT * FROM users WHERE id = ?;", (cursor.lastrowid,)) as cur:
        new_user = await cur.fetchone()
        return dict(new_user)


async def get_user_by_telegram_id(
    db: aiosqlite.Connection, telegram_id: int
) -> Optional[Dict[str, Any]]:
    async with db.execute(
        "SELECT * FROM users WHERE telegram_id = ?;", (telegram_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_user_language(
    db: aiosqlite.Connection, telegram_id: int, til: str
) -> bool:
    await db.execute(
        "UPDATE users SET til = ? WHERE telegram_id = ?;", (til, telegram_id)
    )
    await db.commit()
    return True


async def add_family_member(
    db: aiosqlite.Connection, user_id: int, ism: str, qarindoshlik: Optional[str] = None
) -> int:
    now = get_current_time_str()
    cursor = await db.execute(
        """
        INSERT INTO family_members (user_id, ism, qarindoshlik, yaratilgan_sana)
        VALUES (?, ?, ?, ?);
        """,
        (user_id, ism, qarindoshlik, now)
    )
    await db.commit()
    return cursor.lastrowid


async def get_family_members(
    db: aiosqlite.Connection, user_id: int
) -> List[Dict[str, Any]]:
    async with db.execute(
        "SELECT * FROM family_members WHERE user_id = ? ORDER BY id ASC;", (user_id,)
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def delete_family_member(
    db: aiosqlite.Connection, member_id: int, user_id: int
) -> bool:
    await db.execute(
        "DELETE FROM family_members WHERE id = ? AND user_id = ?;", (member_id, user_id)
    )
    await db.commit()
    return True


async def record_no_show(db: aiosqlite.Connection, user_id: int) -> None:
    """Kelmaslikni qayd qilish va kerak bo'lsa vaqtincha bloklash."""
    async with db.execute("SELECT no_show_count FROM users WHERE id = ?;", (user_id,)) as cursor:
        row = await cursor.fetchone()
        if not row:
            return
        count = (row["no_show_count"] or 0) + 1
        
        blocked_until = None
        if count >= settings.NO_SHOW_THRESHOLD:
            # 14 kunga slot band qilish bloklanadi
            from datetime import timedelta
            blocked_dt = datetime.now(tz) + timedelta(days=settings.NO_SHOW_BLOCK_DAYS)
            blocked_until = blocked_dt.isoformat()
        
        await db.execute(
            """
            UPDATE users SET no_show_count = ?, booking_blocked_until = ?
            WHERE id = ?;
            """,
            (count, blocked_until, user_id)
        )
        await db.commit()


async def unblock_user(db: aiosqlite.Connection, user_id: int) -> bool:
    """Super Admin tomonidan bemorning kelmaslik blokini olib tashlash."""
    await db.execute(
        """
        UPDATE users SET no_show_count = 0, booking_blocked_until = NULL
        WHERE id = ?;
        """,
        (user_id,)
    )
    await db.commit()
    return True


async def get_blocked_users(db: aiosqlite.Connection) -> List[Dict[str, Any]]:
    """Kelmaslik sababli bloklangan yoki ogohlantirilgan bemorlar ro'yxati."""
    async with db.execute(
        """
        SELECT id, telegram_id, ism, telefon, no_show_count, booking_blocked_until
        FROM users
        WHERE no_show_count > 0 OR booking_blocked_until IS NOT NULL
        ORDER BY id DESC;
        """
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def delete_user_data(db: aiosqlite.Connection, telegram_id: int) -> bool:
    """
    Shaxsiy ma'lumotlarni o'chirish (Rozilik va maxfiylik tamoyili bo'yicha).
    Foydalanuvchi va oila a'zolari o'chiriladi, qabullardagi shaxsiy ism/telefon anonimlashtiriladi.
    """
    user = await get_user_by_telegram_id(db, telegram_id)
    if not user:
        return False

    user_id = user["id"]
    await db.execute("BEGIN IMMEDIATE;")
    try:
        # 1. Navbatlardagi ism va telefonni anonimlashtirish
        await db.execute(
            """
            UPDATE appointments
            SET bemor_ismi = 'Anonim Bemor', bemor_telefoni = NULL, user_id = NULL, family_member_id = NULL
            WHERE user_id = ?;
            """,
            (user_id,)
        )
        # 2. Kutish ro'yxatidan o'chirish
        await db.execute("DELETE FROM waitlist WHERE user_id = ?;", (user_id,))
        # 3. Oila a'zolarini o'chirish
        await db.execute("DELETE FROM family_members WHERE user_id = ?;", (user_id,))
        # 4. Foydalanuvchini o'chirish
        await db.execute("DELETE FROM users WHERE id = ?;", (user_id,))
        await db.commit()
        return True
    except Exception:
        await db.rollback()
        raise
