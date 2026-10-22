"""
Xavfsizlik testlari: autentifikatsiya, rollar, IDOR va change-password himoyasi.
"""
import pytest
from httpx import AsyncClient, ASGITransport

from main import app
from app.db.connection import init_db
from app.services.auth_service import generate_session_token
from app.web import deps

ADMIN = {"Authorization": "Bearer " + generate_session_token({"role": "SUPER_ADMIN", "login": "admin"})}


@pytest.fixture(autouse=True)
async def _db():
    await init_db()


def client(headers=None):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers or {})


PROTECTED = [
    ("post", "/api/doctors"),
    ("get", "/api/doctors/1"),
    ("put", "/api/doctors/1"),
    ("delete", "/api/doctors/1"),
    ("post", "/api/doctors/specialties"),
    ("get", "/api/doctors/days-off"),
    ("get", "/api/staff"),
    ("post", "/api/staff/invite"),
    ("delete", "/api/staff/1"),
    ("get", "/api/staff/audit-log"),
    ("get", "/api/staff/blocked-users"),
    ("put", "/api/clinic"),
    ("get", "/api/clinic/kpi"),
    ("get", "/api/queue/today"),
    ("post", "/api/queue/walk-in"),
    ("post", "/api/queue/1/call"),
    ("post", "/api/queue/1/cancel"),
    ("post", "/api/auth/change-password"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", PROTECTED)
async def test_protected_endpoints_reject_anonymous(method, path):
    async with client() as c:
        res = await getattr(c, method)(path)
        assert res.status_code == 401, f"{method} {path} -> {res.status_code}"


@pytest.mark.asyncio
async def test_invalid_token_rejected():
    async with client({"Authorization": "Bearer garbage.token"}) as c:
        assert (await c.get("/api/staff")).status_code == 401


@pytest.mark.asyncio
async def test_public_endpoints_stay_public():
    async with client() as c:
        assert (await c.get("/api/clinic")).status_code == 200
        assert (await c.get("/api/doctors")).status_code == 200
        assert (await c.get("/health")).status_code == 200


@pytest.mark.asyncio
async def test_admin_can_access_protected():
    async with client(ADMIN) as c:
        assert (await c.get("/api/staff")).status_code == 200


@pytest.mark.asyncio
async def test_doctor_cannot_touch_other_doctors_appointment(monkeypatch):
    async def fake_user(request):
        return {"role": "DOCTOR", "doctor_id": 9999, "staff_id": 1}

    async with client(ADMIN) as admin_c:
        docs = (await admin_c.get("/api/doctors")).json()
        walk = await admin_c.post(
            "/api/queue/walk-in",
            json={"doctor_id": docs[0]["id"], "bemor_ismi": "IDOR Test"},
        )
        assert walk.status_code == 200
        app_id = walk.json()["id"]

    monkeypatch.setattr(deps, "resolve_user", fake_user)

    async with client({"X-Telegram-Init-Data": "x"}) as c:
        assert (await c.post(f"/api/queue/{app_id}/call")).status_code == 403
        res = await c.post("/api/queue/walk-in", json={"doctor_id": docs[0]["id"], "bemor_ismi": "Xurshid"})
        assert res.status_code == 403
        # Admin-only marshrutlar doktorga yopiq
        assert (await c.get("/api/staff")).status_code == 403


@pytest.mark.asyncio
async def test_doctor_today_queue_scoped_to_own_doctor(monkeypatch):
    """Shifokor paneli FAQAT o'z navbatini oladi.

    `?doctor_id=<boshqa>` berilsa ham, DOCTOR roli uchun natija o'z `doctor_id` siga
    cheklanishi shart (panellar ajratilganligining API darajasidagi kafolati).
    """
    async with client(ADMIN) as admin_c:
        doc_id = (await admin_c.get("/api/doctors")).json()[0]["id"]
        walk = await admin_c.post(
            "/api/queue/walk-in",
            json={"doctor_id": doc_id, "bemor_ismi": "Panel Scope Test"},
        )
        assert walk.status_code == 200

    async def fake_user(request):
        return {"role": "DOCTOR", "doctor_id": doc_id, "staff_id": 1}

    monkeypatch.setattr(deps, "resolve_user", fake_user)

    async with client({"X-Telegram-Init-Data": "x"}) as c:
        res = await c.get("/api/queue/today?doctor_id=999999")
        assert res.status_code == 200
        apps = res.json()["appointments"]
        assert apps, "Shifokorning o'z navbati qaytishi kerak"
        assert all(a["doctor_id"] == doc_id for a in apps)


@pytest.mark.asyncio
async def test_doctor_cannot_read_other_doctor_details(monkeypatch):
    """Doktor boshqa shifokorning kartochkasi/grafigini ko'ra olmaydi."""
    async def fake_user(request):
        return {"role": "DOCTOR", "doctor_id": 9999, "staff_id": 1}

    monkeypatch.setattr(deps, "resolve_user", fake_user)

    async with client({"X-Telegram-Init-Data": "x"}) as c:
        docs = (await c.get("/api/doctors")).json()  # ro'yxat ochiq
        other_id = docs[0]["id"]
        assert (await c.get(f"/api/doctors/{other_id}")).status_code == 403
        # O'ziga tegishli (mavjud bo'lmagan) shifokor uchun 403 emas, 404 bo'ladi
        assert (await c.get("/api/doctors/9999")).status_code == 404


@pytest.mark.asyncio
async def test_change_password_only_for_own_login():
    async with client(ADMIN) as c:
        res = await c.post(
            "/api/auth/change-password",
            json={"login": "someone_else", "old_password": "x", "new_password": "newpass123"},
        )
        assert res.status_code == 403


@pytest.mark.asyncio
async def test_cannot_revoke_last_super_admin():
    """Oxirgi Super Adminni o'chirish taqiqlangan (WebApp kirishi yopilib qolmasin)."""
    from app.db.connection import get_db

    async with get_db() as db:
        await db.execute("DELETE FROM staff;")
        await db.execute(
            "INSERT INTO staff (telegram_id, rol, faol, biriktirilgan_sana) VALUES (?, 'SUPER_ADMIN', 1, ?);",
            (999000111, "2026-01-01T00:00:00"),
        )
        await db.commit()
        async with db.execute(
            "SELECT id FROM staff WHERE rol = 'SUPER_ADMIN' AND faol = 1 LIMIT 1;"
        ) as cursor:
            row = await cursor.fetchone()
        solo_admin_id = row[0]

    async with client(ADMIN) as c:
        res = await c.delete(f"/api/staff/{solo_admin_id}")
        assert res.status_code == 400

    # Ikkinchi Super Admin qo'shilsa — endi o'chirish mumkin
    async with get_db() as db:
        await db.execute(
            "INSERT INTO staff (telegram_id, rol, faol, biriktirilgan_sana) VALUES (?, 'SUPER_ADMIN', 1, ?);",
            (999000222, "2026-01-01T00:00:00"),
        )
        await db.commit()

    async with client(ADMIN) as c:
        assert (await c.delete(f"/api/staff/{solo_admin_id}")).status_code == 200


def test_production_rejects_default_secrets():
    from app.config import Settings, validate_production_settings

    weak = Settings(ENVIRONMENT="production")
    with pytest.raises(RuntimeError):
        validate_production_settings(weak)

    strong = Settings(
        ENVIRONMENT="production",
        SUPER_ADMIN_PASSWORD="V3ry-Str0ng-Pass!",
        SECRET_KEY="x" * 48,
        BOT_TOKEN="7000000000:AAExampleRealLookingTokenValue1234567",
    )
    validate_production_settings(strong)
