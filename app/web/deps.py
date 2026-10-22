"""
FastAPI autentifikatsiya va rol tekshiruvi (dependency) lari.

Ikki xil kirish usuli qo'llab-quvvatlanadi:
  1. `Authorization: Bearer <token>` — Super Admin sessiya tokeni.
  2. `X-Telegram-Init-Data` — Telegram WebApp (Reception / Doctor xodimlari).
"""
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Request

from app.db.connection import get_db
from app.db.repositories import staff_repo
from app.services.auth_service import validate_telegram_init_data, verify_session_token

ADMIN = "SUPER_ADMIN"
RECEPTION = "RECEPTION"
DOCTOR = "DOCTOR"


async def resolve_user(request: Request) -> Optional[Dict[str, Any]]:
    """So'rovdan foydalanuvchini aniqlaydi. Aniqlanmasa None."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        payload = verify_session_token(auth_header[7:].strip())
        if payload and payload.get("role") == ADMIN:
            return {"role": ADMIN, "login": payload.get("login"), "doctor_id": None}

    init_data = request.headers.get("X-Telegram-Init-Data", "")
    if init_data:
        tg_user = validate_telegram_init_data(init_data)
        if tg_user and tg_user.get("id"):
            async with get_db() as db:
                staff = await staff_repo.get_staff_by_telegram_id(db, tg_user["id"])
            if staff and staff.get("faol", 1):
                return {
                    "role": staff["rol"],
                    "doctor_id": staff.get("doctor_id"),
                    "staff_id": staff["id"],
                }
    return None


def require_role(*roles: str):
    """Berilgan rollardan biri talab qilinadigan dependency yaratadi."""
    allowed = set(roles) | {ADMIN}  # Super Admin hamma narsaga ruxsatli

    async def dependency(request: Request) -> Dict[str, Any]:
        user = await resolve_user(request)
        if user is None:
            raise HTTPException(status_code=401, detail="Autentifikatsiya talab qilinadi.")
        if user["role"] not in allowed:
            raise HTTPException(status_code=403, detail="Ruxsat yo'q.")
        return user

    return dependency


admin_only = Depends(require_role(ADMIN))
staff_user = require_role(RECEPTION, DOCTOR)
