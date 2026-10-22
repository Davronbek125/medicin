"""
FastAPI Xodimlar va Taklif havolalari API.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.config import settings
from app.db.connection import get_db
from app.db.repositories import staff_repo, users_repo
from app.web.deps import require_role, ADMIN

router = APIRouter(prefix="/api/staff", tags=["staff"])


@router.get("/blocked-users", dependencies=[Depends(require_role(ADMIN))])
async def list_blocked_users():
    async with get_db() as db:
        return await users_repo.get_blocked_users(db)


@router.post("/unblock-user/{user_id}", dependencies=[Depends(require_role(ADMIN))])
async def unblock_user(user_id: int):
    async with get_db() as db:
        ok = await users_repo.unblock_user(db, user_id)
        if ok:
            await staff_repo.log_audit_action(db, amal="UNBLOCK_USER", obyekt="users", tafsilot=f"user_id={user_id}")
        return {"success": ok}


@router.get("/audit-log", dependencies=[Depends(require_role(ADMIN))])
async def get_audit_logs(limit: int = 50):
    async with get_db() as db:
        return await staff_repo.get_recent_audit_logs(db, limit=limit)


class InviteCreate(BaseModel):
    rol: str  # 'RECEPTION' yoki 'DOCTOR'
    doctor_id: Optional[int] = None
    hours_valid: int = 24


@router.get("", dependencies=[Depends(require_role(ADMIN))])
async def list_staff():
    async with get_db() as db:
        return await staff_repo.list_all_staff(db)


@router.post("/invite", dependencies=[Depends(require_role(ADMIN))])
async def create_invite(req: InviteCreate):
    if req.rol not in ("RECEPTION", "DOCTOR"):
        raise HTTPException(status_code=400, detail="Noto'g'ri rol.")
    if req.rol == "DOCTOR" and not req.doctor_id:
        raise HTTPException(status_code=400, detail="Shifokor biriktirilishi shart.")

    async with get_db() as db:
        token = await staff_repo.create_invite_token(
            db, rol=req.rol, doctor_id=req.doctor_id, hours_valid=req.hours_valid
        )
        await staff_repo.log_audit_action(
            db, amal="CREATE_INVITE", obyekt="invites", tafsilot=f"rol={req.rol}, doc_id={req.doctor_id}"
        )

    # Bot havolasi (BOT_USERNAME .env da ko'rsatiladi; bo'lmasa umumiy nom)
    bot_username = (settings.BOT_USERNAME or "").strip().lstrip("@") or "clinic_bot"
    invite_url = f"https://t.me/{bot_username}?start=inv_{token}"
    return {"token": token, "invite_url": invite_url, "success": True}


@router.delete("/{staff_id}", dependencies=[Depends(require_role(ADMIN))])
async def revoke_staff(staff_id: int):
    async with get_db() as db:
        target = await staff_repo.get_staff_by_id(db, staff_id)
        if not target:
            raise HTTPException(status_code=404, detail="Xodim topilmadi.")
        # Oxirgi faol Super Adminni o'chirish taqiqlanadi — aks holda Telegram
        # WebApp orqali boshqaruv paneliga kirish butunlay yopilib qoladi.
        if target["rol"] == "SUPER_ADMIN" and target.get("faol", 1):
            if await staff_repo.count_active_super_admins(db) <= 1:
                raise HTTPException(
                    status_code=400,
                    detail="Oxirgi Super Adminni o'chirib bo'lmaydi.",
                )
        ok = await staff_repo.revoke_staff(db, staff_id)
        if ok:
            await staff_repo.log_audit_action(
                db, amal="REVOKE_STAFF", obyekt="staff", tafsilot=f"staff_id={staff_id}"
            )
        return {"success": ok}
