"""
FastAPI Auth API - Super Admin login va Telegram initData tekshiruvi.
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from app.db.connection import get_db
from app.db.repositories import staff_repo
from app.services.auth_service import (
    verify_super_admin, generate_session_token, verify_session_token, validate_telegram_init_data, change_admin_password
)
from app.web.deps import require_role, ADMIN

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    login: str
    password: str


class ChangePasswordRequest(BaseModel):
    login: str
    old_password: str
    new_password: str


@router.post("/login")
async def admin_login(req: LoginRequest):
    async with get_db() as db:
        ok, msg = await verify_super_admin(db, req.login, req.password)
        if not ok:
            raise HTTPException(status_code=401, detail=msg)

    token = generate_session_token({"role": "SUPER_ADMIN", "login": req.login})
    return {"success": True, "token": token, "role": "SUPER_ADMIN"}


@router.post("/change-password")
async def change_password_endpoint(
    req: ChangePasswordRequest, user: dict = Depends(require_role(ADMIN))
):
    # Faqat o'z parolini o'zgartira oladi
    if req.login != user.get("login"):
        raise HTTPException(status_code=403, detail="Faqat o'z parolingizni o'zgartira olasiz.")
    async with get_db() as db:
        # Eski parolni bloklash mexanizmi (lockout) orqali tekshirish
        ok, msg = await verify_super_admin(db, req.login, req.old_password)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        ok, msg = await change_admin_password(db, req.login, req.old_password, req.new_password)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        await staff_repo.log_audit_action(db, amal="CHANGE_PASSWORD", obyekt="admin_security", tafsilot=req.login)
        return {"success": True, "message": msg}


@router.get("/me")
async def get_current_user_profile(request: Request):
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip() if auth_header else ""

    # 1. Session token bormi?
    if token:
        payload = verify_session_token(token)
        if payload:
            return {"authenticated": True, "role": payload.get("role"), "data": payload}

    # 2. Telegram WebApp initData bormi?
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    if init_data:
        tg_user = validate_telegram_init_data(init_data)
        if tg_user:
            tg_id = tg_user.get("id")
            async with get_db() as db:
                staff = await staff_repo.get_staff_by_telegram_id(db, tg_id)
            if staff:
                return {
                    "authenticated": True,
                    "role": staff["rol"],
                    "doctor_id": staff.get("doctor_id"),
                    "staff_id": staff["id"],
                    "name": tg_user.get("first_name", "")
                }

    return {"authenticated": False, "role": "GUEST"}
