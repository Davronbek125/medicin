"""
Xavfsizlik va Autentifikatsiya xizmati - Telegram initData HMAC validatsiyasi va Admin kirishi.
"""
import base64
import hmac
import hashlib
import json
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import aiosqlite
import bcrypt
import pytz
from app.config import settings

tz = pytz.timezone(settings.TIMEZONE)


def validate_telegram_init_data(init_data: str) -> Optional[Dict[str, Any]]:
    """
    Telegram WebApp initData HMAC-SHA256 imzosi va yaroqlilik muddatini tekshirish.
    Soxta so'rovlarning oldini oladi.
    """
    if not init_data:
        return None

    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed_data.pop("hash", None)
        if not received_hash:
            return None

        # Ma'lumotlarni alifbo tartibida saralash
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed_data.items())
        )

        # Telegram algoritmi: secret_key = HMAC_SHA256("WebAppData", bot_token)
        secret_key = hmac.new(
            b"WebAppData", settings.BOT_TOKEN.encode("utf-8"), hashlib.sha256
        ).digest()

        # check_hash = HMAC_SHA256(secret_key, data_check_string)
        calculated_hash = hmac.new(
            secret_key, data_check_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            return None

        # 24 soatlik muddatni tekshirish
        auth_date = int(parsed_data.get("auth_date", 0))
        now_ts = int(datetime.now().timestamp())
        if now_ts - auth_date > 86400:  # 24 soatdan eski
            return None

        user_data = json.loads(parsed_data.get("user", "{}"))
        return user_data

    except Exception:
        return None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception:
        return False


def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")


async def verify_super_admin(
    db: aiosqlite.Connection, login: str, password: str
) -> tuple[bool, str]:
    """Super Admin login-parolini tekshirish va noto'g'ri urinishlarni bloklash."""
    now_dt = datetime.now(tz)
    now_str = now_dt.isoformat()

    async with db.execute(
        "SELECT * FROM admin_security WHERE login = ?;", (login,)
    ) as cursor:
        admin = await cursor.fetchone()
        if not admin:
            return False, "Login yoki parol noto'g'ri."

    # Bloklanganmi tekshirish
    blocked_until_str = admin["blocked_until"]
    if blocked_until_str:
        blocked_until = datetime.fromisoformat(blocked_until_str)
        if now_dt < blocked_until:
            diff_mins = int((blocked_until - now_dt).total_seconds() / 60) + 1
            return False, f"Xavfsizlik sababli tizim bloklangan. {diff_mins} daqiqadan so'ng qayta urinib ko'ring."

    # Parolni tekshirish
    if not verify_password(password, admin["password_hash"]):
        failed = (admin["failed_attempts"] or 0) + 1
        new_blocked = None
        if failed >= settings.MAX_LOGIN_ATTEMPTS:
            new_blocked = (now_dt + timedelta(minutes=settings.LOCKOUT_MINUTES)).isoformat()
            failed = 0  # reset for next cycle after lockout

        await db.execute(
            """
            UPDATE admin_security
            SET failed_attempts = ?, blocked_until = ?
            WHERE id = ?;
            """,
            (failed, new_blocked, admin["id"])
        )
        await db.commit()
        return False, "Login yoki parol noto'g'ri."

    # Muvaffaqiyatli kirish - urinishlarni tozalash
    await db.execute(
        """
        UPDATE admin_security
        SET failed_attempts = 0, blocked_until = NULL, oxirgi_kirish = ?
        WHERE id = ?;
        """,
        (now_str, admin["id"])
    )
    await db.commit()
    return True, "Muvaffaqiyatli."


def generate_session_token(payload: Dict[str, Any], hours: int = 8) -> str:
    """Xavfsiz imzolangan sessiya tokenini yaratish."""
    expire = datetime.now(tz) + timedelta(hours=hours)
    data = {
        "payload": payload,
        "exp": expire.isoformat()
    }
    raw_bytes = json.dumps(data, separators=(",", ":")).encode("utf-8")
    b64_str = base64.urlsafe_b64encode(raw_bytes).decode("ascii")
    sig = hmac.new(settings.SECRET_KEY.encode("utf-8"), b64_str.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64_str}.{sig}"


def verify_session_token(token: str) -> Optional[Dict[str, Any]]:
    """Sessiya tokenini tekshirish."""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        b64_str, sig = parts[0], parts[1]

        calc_sig = hmac.new(
            settings.SECRET_KEY.encode("utf-8"), b64_str.encode("ascii"), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(sig, calc_sig):
            return None

        raw_bytes = base64.urlsafe_b64decode(b64_str.encode("ascii"))
        data = json.loads(raw_bytes.decode("utf-8"))
        exp_dt = datetime.fromisoformat(data["exp"])
        if datetime.now(tz) > exp_dt:
            return None

        return data.get("payload")
    except Exception:
        return None


async def change_admin_password(
    db: aiosqlite.Connection, login: str, old_password: str, new_password: str
) -> tuple[bool, str]:
    """Super Admin parolini almashtirish."""
    if len(new_password) < 6:
        return False, "Yangi parol kamida 6 belgidan iborat bo'lishi kerak."

    async with db.execute(
        "SELECT id, password_hash FROM admin_security WHERE login = ?;", (login,)
    ) as cursor:
        admin = await cursor.fetchone()
        if not admin:
            return False, "Admin topilmadi."

    if not verify_password(old_password, admin["password_hash"]):
        return False, "Eski parol noto'g'ri."

    new_hash = hash_password(new_password)
    await db.execute(
        "UPDATE admin_security SET password_hash = ? WHERE id = ?;",
        (new_hash, admin["id"])
    )
    await db.commit()
    return True, "Parol muvaffaqiyatli o'zgartirildi."
