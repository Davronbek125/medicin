"""
FastAPI Navbatlar API - Jonli tablo, chaqirish, o'tkazish va qo'lda bemor qo'shish.
"""
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
import pytz

from app.config import settings
from app.db.connection import get_db
from app.db.repositories import appointments_repo, doctors_repo, users_repo
from app.services import queue_service, slot_service, notification
from app.web.deps import staff_user

router = APIRouter(prefix="/api/queue", tags=["queue"])
tz = pytz.timezone(settings.TIMEZONE)


async def authorize_appointment(appointment_id: int, user: dict = Depends(staff_user)) -> dict:
    """Navbat mavjudligini va shifokor faqat o'z bemoriga tegishini tekshiradi."""
    async with get_db() as db:
        appt = await appointments_repo.get_appointment_by_id(db, appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Navbat topilmadi.")
    if user["role"] == "DOCTOR" and appt["doctor_id"] != user.get("doctor_id"):
        raise HTTPException(status_code=403, detail="Bu navbat sizga tegishli emas.")
    return user


class WalkInRequest(BaseModel):
    doctor_id: int
    bemor_ismi: str = Field(..., min_length=2, max_length=100)
    bemor_telefoni: Optional[str] = Field(default=None, pattern=r"^\+?[0-9]{9,15}$")

    @field_validator("bemor_telefoni", mode="before")
    @classmethod
    def _blank_phone_to_none(cls, v):
        # Bemor telefoni ixtiyoriy: bo'sh satr yuborilsa uni None ga aylantiramiz,
        # aks holda regex validatsiyasi bo'sh satrni rad etib 422 qaytarardi.
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


@router.get("/today")
async def get_today_queue(
    doctor_id: Optional[int] = None,
    sana: Optional[str] = None,
    user: dict = Depends(staff_user),
):
    """Kunlik navbat/yozilishlar ro'yxati.

    `sana=YYYY-MM-DD` berilsa — o'sha kun uchun qaytariladi (masalan, ertangi
    oldindan yozilishlarni ko'rish uchun). Berilmasa — bugungi kun.
    """
    if user["role"] == "DOCTOR":
        doctor_id = user.get("doctor_id")
        if not doctor_id:
            raise HTTPException(status_code=403, detail="Sizga shifokor profili biriktirilmagan.")

    today_str = datetime.now(tz).strftime("%Y-%m-%d")
    target_date = today_str
    if sana:
        try:
            target_date = datetime.strptime(sana.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Sana formati YYYY-MM-DD bo'lishi kerak.")

    now_hhmm = datetime.now(tz).strftime("%H:%M")
    # PROJECT_PLAN §3.5: slot vaqti boshlangach vaqti kelgan slot bemorlari oldinga chiqadi.
    # Bu faqat BUGUNGI kun uchun mantiqiy — boshqa kunlarda oddiy vaqt tartibida.
    prefer_slots = 1 if (target_date == today_str and now_hhmm >= settings.SLOT_START_TIME) else 0
    async with get_db() as db:
        if doctor_id:
            apps = await appointments_repo.get_today_queue_for_doctor(db, doctor_id, target_date)
        else:
            # Reception uchun barcha shifokorlar navbati (tartib §3.5 bilan mos)
            async with db.execute(
                """
                SELECT a.*, d.ism_uz as doctor_ism, d.xona as doctor_xona, s.nomi_uz as mutaxassislik
                FROM appointments a
                JOIN doctors d ON a.doctor_id = d.id
                LEFT JOIN specialties s ON d.specialty_id = s.id
                WHERE a.sana = ?
                ORDER BY
                    CASE
                        WHEN ? = 1 AND a.turi = 'SLOT' AND a.slot_vaqti IS NOT NULL AND a.slot_vaqti <= ? THEN 0
                        WHEN a.turi = 'LIVE' THEN 1
                        ELSE 2
                    END ASC,
                    CASE WHEN a.turi = 'SLOT' THEN a.slot_vaqti ELSE '99:99' END ASC,
                    a.talon_raqami ASC;
                """,
                (target_date, prefer_slots, now_hhmm)
            ) as cur:
                rows = await cur.fetchall()
                apps = [dict(r) for r in rows]

    return {"sana": target_date, "today": today_str, "appointments": apps}


@router.post("/{appointment_id}/call", dependencies=[Depends(authorize_appointment)])
async def call_patient(appointment_id: int, request: Request):
    """Bemor navbatini chaqirish."""
    # Bot obyektini olish
    bot = getattr(request.app.state, "bot", None)

    async with get_db() as db:
        app = await appointments_repo.get_appointment_by_id(db, appointment_id)
        if not app:
            raise HTTPException(status_code=404, detail="Navbat topilmadi.")

        if app["holat"] in ("YAKUNLANDI", "BEKOR", "MUDDATI_OTDI"):
            raise HTTPException(
                status_code=400,
                detail=f"Yakunlangan yoki bekor qilingan navbatni chaqirib bo'lmaydi (holat: {app['holat']})."
            )

        doc_id = app["doctor_id"]
        today_str = app["sana"]

        # Agar shifokor xonasida oldingi chaqirilgan bemor bo'lsa, uni avtomatik YAKUNLANDI qilish
        async with db.execute(
            """
            SELECT id FROM appointments
            WHERE doctor_id = ? AND sana = ? AND holat = 'CHAQIRILDI' AND id != ?;
            """,
            (doc_id, today_str, appointment_id)
        ) as cur:
            prev_called = await cur.fetchall()
            for p in prev_called:
                await appointments_repo.set_appointment_status(db, p["id"], "YAKUNLANDI")

        # Ushbu bemorni CHAQIRILDI holatiga o'tkazish
        await appointments_repo.set_appointment_status(db, appointment_id, "CHAQIRILDI")

    # Telegram xabari yuborish
    if bot:
        await notification.notify_called(bot, appointment_id)

        # Navbatda 2 kishi qolgan keyingi bemorga ham ogohlantirish yuborish
        async with get_db() as db:
            async with db.execute(
                """
                SELECT id, talon_raqami FROM appointments
                WHERE doctor_id = ? AND sana = ? AND holat = 'KUTMOQDA' AND turi = 'LIVE'
                ORDER BY talon_raqami ASC LIMIT 2;
                """,
                (doc_id, today_str)
            ) as cur:
                waiting_rows = await cur.fetchall()
                if len(waiting_rows) == 2:
                    second_next = waiting_rows[1]
                    _, eta = await queue_service.calculate_live_queue_eta(
                        db, doc_id, today_str, second_next["talon_raqami"]
                    )
                    await notification.notify_approaching(bot, second_next["id"], eta)

    return {"success": True, "status": "CHAQIRILDI"}


@router.post("/{appointment_id}/complete", dependencies=[Depends(authorize_appointment)])
async def complete_appointment(appointment_id: int):
    async with get_db() as db:
        app = await appointments_repo.get_appointment_by_id(db, appointment_id)
        if not app:
            raise HTTPException(status_code=404, detail="Navbat topilmadi.")
        if app["holat"] != "CHAQIRILDI":
            raise HTTPException(
                status_code=400,
                detail=f"Faqat chaqirilgan qabulni yakunlash mumkin (hozirgi holat: {app['holat']})."
            )
        ok = await appointments_repo.set_appointment_status(db, appointment_id, "YAKUNLANDI")
        return {"success": ok, "status": "YAKUNLANDI"}


@router.post("/{appointment_id}/skip", dependencies=[Depends(authorize_appointment)])
async def skip_patient(appointment_id: int):
    async with get_db() as db:
        app = await appointments_repo.get_appointment_by_id(db, appointment_id)
        if not app:
            raise HTTPException(status_code=404, detail="Navbat topilmadi.")
        if app["holat"] == "OTKAZILDI":
            return {"success": True, "status": "OTKAZILDI"}
        if app["holat"] not in ("CHAQIRILDI", "KUTMOQDA"):
            raise HTTPException(
                status_code=400,
                detail=f"Faqat kutayotgan yoki chaqirilgan bemorni o'tkazib yuborish mumkin (holat: {app['holat']})."
            )
        ok = await appointments_repo.set_appointment_status(db, appointment_id, "OTKAZILDI")
        if app.get("user_id"):
            await users_repo.record_no_show(db, app["user_id"])
        return {"success": ok, "status": "OTKAZILDI"}


@router.post("/{appointment_id}/recall", dependencies=[Depends(authorize_appointment)])
async def recall_patient(appointment_id: int):
    """Kechikib kelgan bemorni navbatga qaytarish."""
    async with get_db() as db:
        app = await appointments_repo.get_appointment_by_id(db, appointment_id)
        if not app:
            raise HTTPException(status_code=404, detail="Navbat topilmadi.")
        if app["holat"] != "OTKAZILDI":
            raise HTTPException(
                status_code=400,
                detail=f"Faqat o'tkazib yuborilgan bemorni navbatga qaytarish mumkin (hozirgi holat: {app['holat']})."
            )
        ok = await appointments_repo.set_appointment_status(db, appointment_id, "KUTMOQDA")
        return {"success": ok, "status": "KUTMOQDA"}


@router.post("/{appointment_id}/checkin", dependencies=[Depends(authorize_appointment)])
async def checkin_patient_api(appointment_id: int):
    """Reception tomonidan bemor kelganini belgilash."""
    async with get_db() as db:
        app = await appointments_repo.get_appointment_by_id(db, appointment_id)
        if not app:
            raise HTTPException(status_code=404, detail="Navbat topilmadi.")
        if app["holat"] != "KUTMOQDA":
            raise HTTPException(
                status_code=400,
                detail=f"Faqat kutayotgan navbat uchun kelganlik belgilanadi (holat: {app['holat']})."
            )
        ok = await appointments_repo.check_in_appointment(db, appointment_id)
        return {"success": ok}


@router.post("/{appointment_id}/cancel", dependencies=[Depends(authorize_appointment)])
async def cancel_appointment_api(appointment_id: int, request: Request):
    """Navbatni bekor qilish va waitlist nomzodiga taklif yuborish."""
    bot = getattr(request.app.state, "bot", None)
    async with get_db() as db:
        app = await appointments_repo.get_appointment_by_id(db, appointment_id)
        if not app:
            raise HTTPException(status_code=404, detail="Navbat topilmadi.")
        if app["holat"] not in ("KUTMOQDA", "CHAQIRILDI", "OTKAZILDI"):
            raise HTTPException(
                status_code=400,
                detail=f"Ushbu navbatni bekor qilib bo'lmaydi (holat: {app['holat']})."
            )
        ok = await appointments_repo.cancel_appointment(db, appointment_id)
        if not ok:
            raise HTTPException(status_code=400, detail="Navbatni bekor qilish imkonsiz.")

    # Slot bo'shagan bo'lsa, kutish ro'yxatidagi navbatdagi nomzodga taklif qilish
    if app.get("turi") == "SLOT":
        await slot_service.offer_freed_slot(bot, app["doctor_id"], app["sana"], app["slot_vaqti"])

    return {"success": ok, "status": "BEKOR"}


@router.post("/walk-in")
async def add_walk_in_patient(req: WalkInRequest, user: dict = Depends(staff_user)):
    """Reception tomonidan Telegramsiz bemorni navbatga qo'shish."""
    if user["role"] == "DOCTOR" and req.doctor_id != user.get("doctor_id"):
        raise HTTPException(status_code=403, detail="Boshqa shifokor navbatiga qo'shib bo'lmaydi.")
    today_str = datetime.now(tz).strftime("%Y-%m-%d")
    async with get_db() as db:
        doc = await doctors_repo.get_doctor_by_id(db, req.doctor_id)
        if not doc or doc.get("arxivlangan", 0):
            raise HTTPException(status_code=400, detail="Shifokor topilmadi yoki arxivlangan.")

        app_id, talon_raqami = await appointments_repo.create_live_appointment(
            db,
            doctor_id=req.doctor_id,
            sana=today_str,
            bemor_ismi=req.bemor_ismi,
            bemor_telefoni=req.bemor_telefoni,
            user_id=None,
            family_member_id=None
        )
        return {"id": app_id, "talon_raqami": talon_raqami, "success": True}
