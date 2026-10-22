"""
FastAPI Klinika ma'lumotlari va KPI hisobotlari API.
"""
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import pytz

from app.config import settings
from app.db.connection import get_db
from app.db.repositories import clinic_repo
from app.web.deps import require_role, ADMIN

router = APIRouter(prefix="/api/clinic", tags=["clinic"])
tz = pytz.timezone(settings.TIMEZONE)


class ClinicUpdate(BaseModel):
    nomi_uz: Optional[str] = None
    nomi_ru: Optional[str] = None
    manzil_uz: Optional[str] = None
    manzil_ru: Optional[str] = None
    lokatsiya_lat: Optional[float] = None
    lokatsiya_lon: Optional[float] = None
    telefonlar: Optional[str] = None
    ish_vaqti_uz: Optional[str] = None
    ish_vaqti_ru: Optional[str] = None


@router.get("")
async def get_clinic():
    async with get_db() as db:
        info = await clinic_repo.get_clinic_info(db)
        if not info:
            raise HTTPException(status_code=404, detail="Klinika ma'lumotlari topilmadi.")
        return info


@router.put("", dependencies=[Depends(require_role(ADMIN))])
async def update_clinic(req: ClinicUpdate):
    async with get_db() as db:
        fields = {k: v for k, v in req.model_dump().items() if v is not None}
        ok = await clinic_repo.update_clinic_info(db, **fields)
        return {"success": ok}


@router.get("/kpi", dependencies=[Depends(require_role(ADMIN))])
async def get_kpi_dashboard():
    today_str = datetime.now(tz).strftime("%Y-%m-%d")
    async with get_db() as db:
        return await clinic_repo.get_kpi_stats(db, today_str)
