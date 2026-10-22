"""
Klinika Navbat Tizimi - FastAPI API va WebApp integratsiya testlari.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from main import app
from app.db.connection import init_db
from app.services.i18n import load_locales
from app.services.auth_service import generate_session_token

ADMIN_HEADERS = {
    "Authorization": "Bearer " + generate_session_token({"role": "SUPER_ADMIN", "login": "admin"})
}


@pytest.fixture(autouse=True)
async def setup_api_db():
    await init_db()
    load_locales()


@pytest.mark.asyncio
async def test_health_check():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=ADMIN_HEADERS) as client:
        res = await client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_clinic_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=ADMIN_HEADERS) as client:
        res = await client.get("/api/clinic")
        assert res.status_code == 200
        data = res.json()
        assert "Shifo" in data["nomi_uz"]


@pytest.mark.asyncio
async def test_doctors_and_queue_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=ADMIN_HEADERS) as client:
        # Shifokorlar ro'yxati
        res = await client.get("/api/doctors")
        assert res.status_code == 200
        docs = res.json()
        assert len(docs) >= 1
        doc_id = docs[0]["id"]

        # Reception walk-in bemor qo'shadi
        res_walk = await client.post(
            "/api/queue/walk-in",
            json={"doctor_id": doc_id, "bemor_ismi": "Salim Bobo", "bemor_telefoni": "+998901234567"}
        )
        assert res_walk.status_code == 200
        walk_data = res_walk.json()
        assert walk_data["talon_raqami"] >= 1
        app_id = walk_data["id"]

        # Bugungi navbat tablosini olish
        res_queue = await client.get(f"/api/queue/today?doctor_id={doc_id}")
        assert res_queue.status_code == 200
        queue_data = res_queue.json()
        assert any(a["id"] == app_id for a in queue_data["appointments"])

        # Bemor chaqiriladi
        res_call = await client.post(f"/api/queue/{app_id}/call")
        assert res_call.status_code == 200

        # Qabul yakunlanadi
        res_comp = await client.post(f"/api/queue/{app_id}/complete")
        assert res_comp.status_code == 200


@pytest.mark.asyncio
async def test_html_pages_render():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=ADMIN_HEADERS) as client:
        for path in ["/", "/admin", "/reception", "/doctor?doctor_id=1"]:
            res = await client.get(path)
            assert res.status_code == 200
            assert "html" in res.headers["content-type"]


@pytest.mark.asyncio
async def test_queue_checkin_and_cancel_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=ADMIN_HEADERS) as client:
        # Get doctor
        res_docs = await client.get("/api/doctors")
        doc_id = res_docs.json()[0]["id"]

        # Add walk-in
        res_walk = await client.post(
            "/api/queue/walk-in",
            json={"doctor_id": doc_id, "bemor_ismi": "Checkin Test", "bemor_telefoni": "+998901234567"}
        )
        app_id = res_walk.json()["id"]

        # Check in
        res_checkin = await client.post(f"/api/queue/{app_id}/checkin")
        assert res_checkin.status_code == 200
        assert res_checkin.json()["success"] is True

        # Cancel
        res_cancel = await client.post(f"/api/queue/{app_id}/cancel")
        assert res_cancel.status_code == 200
        assert res_cancel.json()["success"] is True
        assert res_cancel.json()["status"] == "BEKOR"


@pytest.mark.asyncio
async def test_staff_blocked_users_and_password_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=ADMIN_HEADERS) as client:
        # Blocked users list
        res_blocked = await client.get("/api/staff/blocked-users")
        assert res_blocked.status_code == 200
        assert isinstance(res_blocked.json(), list)

        # Unblock non-existent or existing
        res_unblock = await client.post("/api/staff/unblock-user/99999")
        assert res_unblock.status_code == 200
        assert res_unblock.json()["success"] is True

        # Change password bad old password
        res_pw_bad = await client.post(
            "/api/auth/change-password",
            json={"login": "admin", "old_password": "wrong_password", "new_password": "new_password_123"}
        )
        assert res_pw_bad.status_code == 400

        # Test noto'g'ri urinishi admin akkauntini bloklab qo'ymasligi uchun hisoblagichni tozalaymiz
        from app.db.connection import get_db
        async with get_db() as db:
            await db.execute("UPDATE admin_security SET failed_attempts = 0, blocked_until = NULL;")
            await db.commit()

        # Audit log endpoint
        res_audit = await client.get("/api/staff/audit-log")
        assert res_audit.status_code == 200
        assert isinstance(res_audit.json(), list)

        # Enriched KPI endpoint
        res_kpi = await client.get("/api/clinic/kpi")
        assert res_kpi.status_code == 200
        kpi_data = res_kpi.json()
        assert "ortacha_kutish_vaqti" in kpi_data
        assert "kelmaslik_foizi" in kpi_data
        assert "bot_orqali" in kpi_data
        assert "reception_orqali" in kpi_data


@pytest.mark.asyncio
async def test_telegram_webhook_secret_verification():
    from app.config import settings
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Noto'g'ri secret token -> 403
        bad_res = await client.post(
            "/api/bot/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "bad_secret"},
            json={"update_id": 1}
        )
        assert bad_res.status_code == 403

        # To'g'ri secret token -> 200
        correct_secret = settings.SECRET_KEY[:32]
        good_res = await client.post(
            "/api/bot/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": correct_secret},
            json={"update_id": 100}
        )
        assert good_res.status_code == 200


@pytest.mark.asyncio
async def test_queue_by_date_param():
    """`sana` parametri boshqa kundagi oldindan yozilishlarni ham qaytarishi kerak.

    Muammo: bemor bot orqali ertangi kunga slot band qilganda, qabulxona va
    shifokor panellari faqat BUGUNGI navbatni ko'rsatgani uchun yozuv
    ko'rinmas edi.
    """
    from datetime import datetime, timedelta
    import pytz
    from app.config import settings
    from app.db.connection import get_db
    from app.db.repositories import appointments_repo

    tz = pytz.timezone(settings.TIMEZONE)
    future = (datetime.now(tz) + timedelta(days=3)).strftime("%Y-%m-%d")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=ADMIN_HEADERS) as client:
        res = await client.get("/api/doctors")
        doc_id = res.json()[0]["id"]

        async with get_db() as db:
            app_id, _ = await appointments_repo.create_slot_appointment(
                db,
                doctor_id=doc_id,
                sana=future,
                slot_vaqti="15:00",
                bemor_ismi="Kelgusi Bemor",
            )

        # Tanlangan sana bo'yicha yozuv qaytadi
        res_future = await client.get(f"/api/queue/today?sana={future}&doctor_id={doc_id}")
        assert res_future.status_code == 200
        data = res_future.json()
        assert data["sana"] == future
        assert any(a["id"] == app_id for a in data["appointments"])

        # Bugungi ro'yxatda bu yozuv bo'lmasligi kerak
        res_today = await client.get(f"/api/queue/today?doctor_id={doc_id}")
        assert all(a["id"] != app_id for a in res_today.json()["appointments"])

        # Noto'g'ri sana formati -> 400
        res_bad = await client.get("/api/queue/today?sana=2026-13-99")
        assert res_bad.status_code == 400
