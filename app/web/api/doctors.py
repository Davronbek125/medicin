"""
FastAPI Shifokorlar va Mutaxassisliklar API.
"""
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
import pytz
from app.config import settings
from app.db.connection import get_db
from app.db.repositories import doctors_repo, appointments_repo, staff_repo
from app.services import notification
from app.web.deps import require_role, ADMIN, staff_user

router = APIRouter(prefix="/api/doctors", tags=["doctors"])
tz = pytz.timezone(settings.TIMEZONE)


class SpecialtyCreate(BaseModel):
    nomi_uz: str
    nomi_ru: str
    tartib: int = 0


class DoctorCreate(BaseModel):
    specialty_id: int
    ism_uz: str
    ism_ru: str
    xona: str
    tajriba_yili: int = 0
    tavsif_uz: Optional[str] = None
    tavsif_ru: Optional[str] = None
    ortacha_vaqt: int = 15
    rasm_url: Optional[str] = None
    botda_korinadi: int = 1
    tartib: int = 0


class DoctorUpdate(BaseModel):
    specialty_id: Optional[int] = None
    ism_uz: Optional[str] = None
    ism_ru: Optional[str] = None
    xona: Optional[str] = None
    tajriba_yili: Optional[int] = None
    tavsif_uz: Optional[str] = None
    tavsif_ru: Optional[str] = None
    ortacha_vaqt: Optional[int] = None
    rasm_url: Optional[str] = None
    botda_korinadi: Optional[int] = None
    tartib: Optional[int] = None


class ScheduleDayUpdate(BaseModel):
    hafta_kuni: int
    jonli_boshlanish: str = "10:00"
    jonli_tugash: str = "15:00"
    slot_boshlanish: str = "15:00"
    slot_tugash: str = "16:00"
    faol: int = 1


class DayOffCreate(BaseModel):
    sana: str
    doctor_id: Optional[int] = None
    sabab: Optional[str] = None


# --- Mutaxassisliklar ---
@router.get("/specialties")
async def list_specialties():
    async with get_db() as db:
        return await doctors_repo.get_all_specialties(db)


@router.post("/specialties", dependencies=[Depends(require_role(ADMIN))])
async def add_specialty(req: SpecialtyCreate):
    async with get_db() as db:
        new_id = await doctors_repo.create_specialty(db, req.nomi_uz, req.nomi_ru, req.tartib)
        return {"id": new_id, "success": True}


@router.delete("/specialties/{spec_id}", dependencies=[Depends(require_role(ADMIN))])
async def remove_specialty(spec_id: int):
    async with get_db() as db:
        await doctors_repo.delete_specialty(db, spec_id)
        return {"success": True}


# --- Shifokorlar ---
@router.get("")
async def list_doctors(include_archived: bool = False):
    async with get_db() as db:
        return await doctors_repo.get_all_doctors(db, include_archived=include_archived)


@router.get("/days-off", dependencies=[Depends(require_role(ADMIN))])
async def list_days_off():
    """Belgilangan dam olish kunlari va ta'tillar ro'yxati."""
    async with get_db() as db:
        async with db.execute(
            """
            SELECT d_off.*, d.ism_uz as doctor_name
            FROM days_off d_off
            LEFT JOIN doctors d ON d_off.doctor_id = d.id
            ORDER BY d_off.sana DESC;
            """
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


@router.post("/days-off", dependencies=[Depends(require_role(ADMIN))])
async def set_doctor_day_off(req: DayOffCreate, request: Request):
    bot = getattr(request.app.state, "bot", None)
    async with get_db() as db:
        new_id = await doctors_repo.set_day_off(db, req.sana, req.doctor_id, req.sabab)
        await staff_repo.log_audit_action(
            db, amal="SET_DAY_OFF", obyekt="days_off", tafsilot=f"doc_id={req.doctor_id}, sana={req.sana}"
        )
        # Shu kundagi navbatlarni bekor qilish
        cancelled = await appointments_repo.cancel_appointments_for_date(db, req.doctor_id, req.sana)
    # Bemorlarga bildirishnoma yuborish (bekor qilishdan OLDIN olingan ro'yxat bo'yicha)
    notified = 0
    if bot and cancelled:
        notified = await notification.notify_cancelled_by_clinic(bot, cancelled)
    return {"id": new_id, "cancelled_count": len(cancelled), "notified_count": notified, "success": True}


@router.get("/{doctor_id}")
async def get_doctor_details(doctor_id: int, user: dict = Depends(staff_user)):
    """Shifokor tafsilotlari va ish grafigi (faqat xodimlar uchun).

    Shifokor FAQAT o'z kartochkasini ko'radi; qabulxona va Super Admin istalgan
    shifokorning ma'lumotlarini ko'rishi mumkin (navbatni boshqarish uchun zarur).
    """
    if user["role"] == "DOCTOR" and user.get("doctor_id") != doctor_id:
        raise HTTPException(status_code=403, detail="Bu shifokor ma'lumotlari sizga tegishli emas.")
    async with get_db() as db:
        doc = await doctors_repo.get_doctor_by_id(db, doctor_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Shifokor topilmadi.")
        schedules = await doctors_repo.get_doctor_schedules(db, doctor_id)
        return {"doctor": doc, "schedules": schedules}


@router.post("", dependencies=[Depends(require_role(ADMIN))])
async def add_doctor(req: DoctorCreate):
    async with get_db() as db:
        new_id = await doctors_repo.create_doctor(
            db,
            specialty_id=req.specialty_id,
            ism_uz=req.ism_uz,
            ism_ru=req.ism_ru,
            xona=req.xona,
            tajriba_yili=req.tajriba_yili,
            tavsif_uz=req.tavsif_uz,
            tavsif_ru=req.tavsif_ru,
            ortacha_vaqt=req.ortacha_vaqt,
            rasm_url=req.rasm_url,
            botda_korinadi=req.botda_korinadi,
            tartib=req.tartib
        )
        await staff_repo.log_audit_action(
            db, amal="ADD_DOCTOR", obyekt="doctors", tafsilot=f"doc_id={new_id}, ism={req.ism_uz}"
        )
        return {"id": new_id, "success": True}


@router.put("/{doctor_id}", dependencies=[Depends(require_role(ADMIN))])
async def edit_doctor(doctor_id: int, req: DoctorUpdate):
    async with get_db() as db:
        fields = {k: v for k, v in req.model_dump().items() if v is not None}
        ok = await doctors_repo.update_doctor(db, doctor_id, **fields)
        if ok:
            await staff_repo.log_audit_action(
                db, amal="EDIT_DOCTOR", obyekt="doctors", tafsilot=f"doc_id={doctor_id}"
            )
        return {"success": ok}


@router.delete("/{doctor_id}", dependencies=[Depends(require_role(ADMIN))])
async def archive_doctor_endpoint(doctor_id: int, request: Request):
    bot = getattr(request.app.state, "bot", None)
    cancelled_all = []
    async with get_db() as db:
        ok = await doctors_repo.archive_doctor(db, doctor_id)
        if ok:
            await staff_repo.log_audit_action(
                db, amal="ARCHIVE_DOCTOR", obyekt="doctors", tafsilot=f"doc_id={doctor_id}"
            )
        today_str = datetime.now(tz).strftime("%Y-%m-%d")
        async with db.execute(
            "SELECT DISTINCT sana FROM appointments WHERE doctor_id = ? AND sana >= ? AND holat IN ('KUTMOQDA', 'CHAQIRILDI');",
            (doctor_id, today_str)
        ) as cur:
            dates = await cur.fetchall()
            for d in dates:
                cancelled = await appointments_repo.cancel_appointments_for_date(db, doctor_id, d["sana"])
                cancelled_all.extend(cancelled)
    # Bemolarga bekor qilish haqida xabar (bekor qilishdan OLDIN olingan ro'yxat bo'yicha)
    if bot and cancelled_all:
        await notification.notify_cancelled_by_clinic(bot, cancelled_all)
    return {"success": ok, "cancelled_count": len(cancelled_all)}


# --- Ish grafigi va ta'tillar ---
@router.put("/{doctor_id}/schedules", dependencies=[Depends(require_role(ADMIN))])
async def update_schedules(doctor_id: int, schedules: List[ScheduleDayUpdate]):
    async with get_db() as db:
        for s in schedules:
            await doctors_repo.update_doctor_schedule_day(
                db,
                doctor_id=doctor_id,
                hafta_kuni=s.hafta_kuni,
                jonli_boshlanish=s.jonli_boshlanish,
                jonli_tugash=s.jonli_tugash,
                slot_boshlanish=s.slot_boshlanish,
                slot_tugash=s.slot_tugash,
                faol=s.faol
            )
        return {"success": True}
