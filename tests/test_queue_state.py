"""
Navbat holatlari mashinasi (State Machine) va validatsiya testlari.
"""
import pytest
from httpx import AsyncClient, ASGITransport

from main import app
from app.db.connection import init_db
from app.services.auth_service import generate_session_token

ADMIN_HEADERS = {
    "Authorization": "Bearer " + generate_session_token({"role": "SUPER_ADMIN", "login": "admin"})
}


@pytest.fixture(autouse=True)
async def _setup_db():
    await init_db()


def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=ADMIN_HEADERS)


@pytest.mark.asyncio
async def test_queue_state_transitions():
    async with client() as c:
        # Shifokor olish
        docs = (await c.get("/api/doctors")).json()
        doc_id = docs[0]["id"]

        # 1. Yangi bemor qo'shish (holati: KUTMOQDA)
        res_walk = await c.post(
            "/api/queue/walk-in",
            json={"doctor_id": doc_id, "bemor_ismi": "Alisher Navoiy", "bemor_telefoni": "+998901112233"}
        )
        assert res_walk.status_code == 200
        app_id = res_walk.json()["id"]

        # 2. KUTMOQDA turgan bemorni birdaniga COMPLETE qilib bo'lmaydi (faqat CHAQIRILDI holatidan)
        res_comp_bad = await c.post(f"/api/queue/{app_id}/complete")
        assert res_comp_bad.status_code == 400

        # 3. KUTMOQDA turgan bemorni RECALL qilib bo'lmaydi (faqat OTKAZILDI dan)
        res_recall_bad = await c.post(f"/api/queue/{app_id}/recall")
        assert res_recall_bad.status_code == 400

        # 4. CHAQIRISH (KUTMOQDA -> CHAQIRILDI)
        res_call = await c.post(f"/api/queue/{app_id}/call")
        assert res_call.status_code == 200
        assert res_call.json()["status"] == "CHAQIRILDI"

        # 5. QABULNI YAKUNLASH (CHAQIRILDI -> YAKUNLANDI)
        res_comp = await c.post(f"/api/queue/{app_id}/complete")
        assert res_comp.status_code == 200
        assert res_comp.json()["status"] == "YAKUNLANDI"

        # 6. YAKUNLANGAN navbatni qayta chaqirib yoki bekor qilib bo'lmaydi
        res_call_again = await c.post(f"/api/queue/{app_id}/call")
        assert res_call_again.status_code == 400

        res_cancel_done = await c.post(f"/api/queue/{app_id}/cancel")
        assert res_cancel_done.status_code == 400


@pytest.mark.asyncio
async def test_skip_and_recall_flow_with_idempotency():
    async with client() as c:
        docs = (await c.get("/api/doctors")).json()
        doc_id = docs[0]["id"]

        # Yangi bemor
        res_walk = await c.post(
            "/api/queue/walk-in",
            json={"doctor_id": doc_id, "bemor_ismi": "Bobur Mirzo"}
        )
        app_id = res_walk.json()["id"]

        # Kelmadi (KUTMOQDA -> OTKAZILDI)
        res_skip = await c.post(f"/api/queue/{app_id}/skip")
        assert res_skip.status_code == 200
        assert res_skip.json()["status"] == "OTKAZILDI"

        # Takroriy skip qilish xato bermaydi va statusni o'zgartirmaydi (idempotent)
        res_skip2 = await c.post(f"/api/queue/{app_id}/skip")
        assert res_skip2.status_code == 200
        assert res_skip2.json()["status"] == "OTKAZILDI"

        # Kechikib kelgan bemorni navbatga qaytarish (OTKAZILDI -> KUTMOQDA)
        res_recall = await c.post(f"/api/queue/{app_id}/recall")
        assert res_recall.status_code == 200
        assert res_recall.json()["status"] == "KUTMOQDA"


@pytest.mark.asyncio
async def test_walk_in_validation():
    async with client() as c:
        docs = (await c.get("/api/doctors")).json()
        doc_id = docs[0]["id"]

        # Juda qisqa ism (1 belgi) -> 422
        res1 = await c.post("/api/queue/walk-in", json={"doctor_id": doc_id, "bemor_ismi": "A"})
        assert res1.status_code == 422

        # Noto'g'ri telefon formati -> 422
        res2 = await c.post("/api/queue/walk-in", json={"doctor_id": doc_id, "bemor_ismi": "Ali", "bemor_telefoni": "telefon"})
        assert res2.status_code == 422

        # Mavjud bo'lmagan shifokor -> 400
        res3 = await c.post("/api/queue/walk-in", json={"doctor_id": 999999, "bemor_ismi": "Vali"})
        assert res3.status_code == 400


@pytest.mark.asyncio
async def test_walk_in_optional_phone():
    """Telefon ixtiyoriy: bo'sh satr yuborilsa ham bemor qo'shilishi kerak (avval 422 edi)."""
    async with client() as c:
        docs = (await c.get("/api/doctors")).json()
        doc_id = docs[0]["id"]

        res = await c.post(
            "/api/queue/walk-in",
            json={"doctor_id": doc_id, "bemor_ismi": "Telefonsiz Bemor", "bemor_telefoni": ""},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["talon_raqami"] >= 1

        # Maydon umuman yuborilmasa ham ishlashi kerak
        res2 = await c.post(
            "/api/queue/walk-in",
            json={"doctor_id": doc_id, "bemor_ismi": "Nomsiz Telefon"},
        )
        assert res2.status_code == 200
