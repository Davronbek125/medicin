"""
Klinika Navbat Tizimi - Asosiy xizmatlar va repo testlari.
"""
import pytest
import os
from datetime import datetime
from app.config import settings
from app.db.connection import get_db, init_db
from app.db.repositories import (
    users_repo, doctors_repo, appointments_repo
)
from app.services import queue_service, slot_service, auth_service, i18n

# Testlar uchun vaqtinchalik test bazasidan foydalanish
os.environ["DB_PATH"] = "data/test_clinic.db"
settings.DB_PATH = "data/test_clinic.db"


@pytest.fixture(autouse=True)
async def setup_test_db():
    if os.path.exists(settings.DB_PATH):
        try:
            os.remove(settings.DB_PATH)
        except Exception:
            pass
    await init_db()
    i18n.load_locales()
    yield
    if os.path.exists(settings.DB_PATH):
        try:
            os.remove(settings.DB_PATH)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_users_and_family():
    async with get_db() as db:
        # User yaratish
        user = await users_repo.get_or_create_user(
            db, telegram_id=999888, ism="Ali Valiyev", telefon="+998901112233", til="uz"
        )
        assert user["telegram_id"] == 999888
        assert user["ism"] == "Ali Valiyev"

        # Oila a'zosi qo'shish
        fam_id = await users_repo.add_family_member(
            db, user_id=user["id"], ism="Olim Valiyev", qarindoshlik="Farzand"
        )
        assert fam_id > 0

        members = await users_repo.get_family_members(db, user_id=user["id"])
        assert len(members) == 1
        assert members[0]["ism"] == "Olim Valiyev"


@pytest.mark.asyncio
async def test_doctors_and_appointments():
    async with get_db() as db:
        doctors = await doctors_repo.get_all_doctors(db)
        assert len(doctors) >= 1
        doc = doctors[0]

        today_str = datetime.now().strftime("%Y-%m-%d")

        # 1-bemor jonli navbat oladi
        app_id_1, t_num_1 = await appointments_repo.create_live_appointment(
            db, doctor_id=doc["id"], sana=today_str, bemor_ismi="Bemor 1"
        )
        assert t_num_1 == 1

        # 2-bemor jonli navbat oladi
        app_id_2, t_num_2 = await appointments_repo.create_live_appointment(
            db, doctor_id=doc["id"], sana=today_str, bemor_ismi="Bemor 2"
        )
        assert t_num_2 == 2

        # 2-bemor oldidagi odamlar soni
        ahead = await appointments_repo.count_waiting_before(
            db, doctor_id=doc["id"], sana=today_str, talon_raqami=t_num_2
        )
        assert ahead == 1

        # 1-bemor navbati chaqiriladi
        await appointments_repo.set_appointment_status(db, app_id_1, "CHAQIRILDI")
        app1 = await appointments_repo.get_appointment_by_id(db, app_id_1)
        assert app1["holat"] == "CHAQIRILDI"
        assert app1["called_at"] is not None


@pytest.mark.asyncio
async def test_slot_service():
    async with get_db() as db:
        doctors = await doctors_repo.get_all_doctors(db)
        doc = doctors[0]

        dates = await slot_service.get_available_booking_dates(db, doc["id"], days_ahead=7)
        assert len(dates) > 0

        target_date = dates[0]["sana"]
        slots = await slot_service.get_available_slots_for_date(db, doc["id"], target_date)
        assert len(slots) > 0


@pytest.mark.asyncio
async def test_auth_service():
    async with get_db() as db:
        ok, msg = await auth_service.verify_super_admin(
            db, login=settings.SUPER_ADMIN_LOGIN, password=settings.SUPER_ADMIN_PASSWORD
        )
        assert ok is True

        wrong_ok, wrong_msg = await auth_service.verify_super_admin(
            db, login=settings.SUPER_ADMIN_LOGIN, password="wrongpassword"
        )
        assert wrong_ok is False

        # Session token
        token = auth_service.generate_session_token({"role": "SUPER_ADMIN", "login": "admin"})
        payload = auth_service.verify_session_token(token)
        assert payload is not None
        assert payload["role"] == "SUPER_ADMIN"


@pytest.mark.asyncio
async def test_waitlist_flow():
    async with get_db() as db:
        user = await users_repo.get_or_create_user(
            db, telegram_id=1234567, ism="Waitlist Patient", telefon="+998901234567"
        )
        doctors = await doctors_repo.get_all_doctors(db)
        doc_id = doctors[0]["id"]
        target_date = "2026-10-20"

        # Add to waitlist
        w_id = await appointments_repo.add_to_waitlist(
            db, doctor_id=doc_id, sana=target_date, user_id=user["id"], bemor_ismi="Waitlist Patient"
        )
        assert w_id > 0

        # Candidate check
        cand = await appointments_repo.get_next_waitlist_candidate(
            db, doctor_id=doc_id, sana=target_date
        )
        assert cand is not None
        assert cand["id"] == w_id
        assert cand["user_tg_id"] == 1234567

        # Status update
        await appointments_repo.set_waitlist_status(db, w_id, "TAKLIF_YUBORILDI")
        cand_after = await appointments_repo.get_next_waitlist_candidate(
            db, doctor_id=doc_id, sana=target_date
        )
        assert cand_after is None


@pytest.mark.asyncio
async def test_waitlist_offer_expiry_and_accept():
    """Taklif muddati tugashi, slot vaqtini eslab qolish va QABUL_QILINDI holati."""
    async with get_db() as db:
        doctors = await doctors_repo.get_all_doctors(db)
        doc_id = doctors[0]["id"]
        sana = "2026-10-20"
        u1 = await users_repo.get_or_create_user(db, telegram_id=1001, ism="Ali", telefon="+998900000001")
        u2 = await users_repo.get_or_create_user(db, telegram_id=1002, ism="Vali", telefon="+998900000002")
        w1 = await appointments_repo.add_to_waitlist(db, doc_id, sana, u1["id"], "Ali")
        w2 = await appointments_repo.add_to_waitlist(db, doc_id, sana, u2["id"], "Vali")

        # 1-nomzodga slot taklif qilinadi (slot_vaqti saqlanadi)
        await appointments_repo.set_waitlist_status(db, w1, "TAKLIF_YUBORILDI", slot_vaqti="15:00")

        # Muddati o'tgan taklifni yopish (kelajakdagi cutoff -> yozuv eski hisoblanadi)
        expired = await appointments_repo.expire_stale_waitlist_offers(db, "2999-01-01T00:00:00")
        assert any(e["id"] == w1 and e["taklif_slot_vaqti"] == "15:00" for e in expired)

        # w1 endi MUDDATI_OTDI -> navbatdagi nomzod w2
        cand = await appointments_repo.get_next_waitlist_candidate(db, doc_id, sana)
        assert cand is not None and cand["id"] == w2

        # w2 taklifni qabul qiladi -> QABUL_QILINDI
        await appointments_repo.set_waitlist_status(db, w2, "TAKLIF_YUBORILDI", slot_vaqti="15:00")
        updated = await appointments_repo.mark_waitlist_accepted(db, u2["id"], doc_id, sana)
        assert updated == 1
        assert await appointments_repo.get_next_waitlist_candidate(db, doc_id, sana) is None


@pytest.mark.asyncio
async def test_offer_freed_slot_sets_status_and_skips_occupied():
    """offer_freed_slot bo'sh slotni taklif qiladi, band slotni esa o'tkazib yuboradi."""
    from app.services import slot_service

    async with get_db() as db:
        doctors = await doctors_repo.get_all_doctors(db)
        doc_id = doctors[0]["id"]
        sana = "2026-10-20"
        user = await users_repo.get_or_create_user(db, telegram_id=2001, ism="Karim", telefon="+998900000003")
        await appointments_repo.add_to_waitlist(db, doc_id, sana, user["id"], "Karim")

    # Bo'sh slot (bot=None bo'lsa ham holat o'zgaradi)
    assert await slot_service.offer_freed_slot(None, doc_id, sana, "15:00") is True
    async with get_db() as db:
        assert await appointments_repo.get_next_waitlist_candidate(db, doc_id, sana) is None

    # Band slot -> taklif qilinmaydi
    async with get_db() as db:
        await appointments_repo.create_slot_appointment(
            db, doctor_id=doc_id, sana=sana, slot_vaqti="15:20", bemor_ismi="Band Bemor"
        )
        user2 = await users_repo.get_or_create_user(db, telegram_id=2002, ism="Sobir", telefon="+998900000004")
        await appointments_repo.add_to_waitlist(db, doc_id, sana, user2["id"], "Sobir")

    assert await slot_service.offer_freed_slot(None, doc_id, sana, "15:20") is False
    async with get_db() as db:
        cand = await appointments_repo.get_next_waitlist_candidate(db, doc_id, sana)
        assert cand is not None and cand["id"] == user2["id"]


@pytest.mark.asyncio
async def test_no_show_and_unblock():
    async with get_db() as db:
        user = await users_repo.get_or_create_user(
            db, telegram_id=777888, ism="Late Patient", telefon="+998909998877"
        )
        # 1st no-show
        await users_repo.record_no_show(db, user["id"])
        u1 = await users_repo.get_user_by_telegram_id(db, 777888)
        assert u1["no_show_count"] == 1

        # 2nd no-show
        await users_repo.record_no_show(db, user["id"])
        u2 = await users_repo.get_user_by_telegram_id(db, 777888)
        assert u2["no_show_count"] == 2

        # 3rd no-show -> reaches threshold
        await users_repo.record_no_show(db, user["id"])
        u3 = await users_repo.get_user_by_telegram_id(db, 777888)
        assert u3["no_show_count"] == 3
        assert u3["booking_blocked_until"] is not None

        # Check blocked list
        blocked = await users_repo.get_blocked_users(db)
        assert any(b["id"] == user["id"] for b in blocked)

        # Unblock
        await users_repo.unblock_user(db, user["id"])
        u_unblocked = await users_repo.get_user_by_telegram_id(db, 777888)
        assert u_unblocked["no_show_count"] == 0
        assert u_unblocked["booking_blocked_until"] is None


@pytest.mark.asyncio
async def test_doctor_day_off_and_cancellation():
    async with get_db() as db:
        doctors = await doctors_repo.get_all_doctors(db)
        doc_id = doctors[0]["id"]
        day_str = "2026-10-25"

        # Create appointment on that date
        app_id, talon = await appointments_repo.create_slot_appointment(
            db, doctor_id=doc_id, sana=day_str, slot_vaqti="15:00", bemor_ismi="Slot Patient"
        )
        assert app_id > 0

        # Set day off
        await doctors_repo.set_day_off(db, sana=day_str, doctor_id=doc_id, sabab="Seminar")
        is_off = await doctors_repo.is_doctor_off_on_date(db, doc_id, day_str)
        assert is_off is True

        # Cancel appointments on that date
        cancelled = await appointments_repo.cancel_appointments_for_date(db, doc_id, day_str)
        assert len(cancelled) == 1
        assert cancelled[0]["id"] == app_id

        app_check = await appointments_repo.get_appointment_by_id(db, app_id)
        assert app_check["holat"] == "BEKOR"


@pytest.mark.asyncio
async def test_change_admin_password():
    async with get_db() as db:
        # Wrong old password
        ok, msg = await auth_service.change_admin_password(db, "admin", "wrong_old", "new_secret_123")
        assert ok is False

        # Correct old password
        ok, msg = await auth_service.change_admin_password(
            db, "admin", settings.SUPER_ADMIN_PASSWORD, "new_secret_123"
        )
        assert ok is True

        # Verify login with new password
        ok_new, _ = await auth_service.verify_super_admin(db, "admin", "new_secret_123")
        assert ok_new is True

        # Restore original password for other tests
        await auth_service.change_admin_password(db, "admin", "new_secret_123", settings.SUPER_ADMIN_PASSWORD)


@pytest.mark.asyncio
async def test_count_waiting_before_excludes_slots():
    """Jonli navbat ETA si faqat jonli navbatdagilarni sanashi kerak (slot bemorlari emas)."""
    async with get_db() as db:
        doctors = await doctors_repo.get_all_doctors(db)
        doc = doctors[0]
        today = datetime.now().strftime("%Y-%m-%d")

        # Oldindan yozilgan slot past talon raqamini oladi
        await appointments_repo.create_slot_appointment(
            db, doctor_id=doc["id"], sana=today, slot_vaqti="15:00", bemor_ismi="Slot 1"
        )
        _, _ = await appointments_repo.create_live_appointment(
            db, doctor_id=doc["id"], sana=today, bemor_ismi="Jonli 1"
        )
        _, live2_talon = await appointments_repo.create_live_appointment(
            db, doctor_id=doc["id"], sana=today, bemor_ismi="Jonli 2"
        )

        # Barcha turlar bo'yicha oldinda: slot(1) + jonli(1) = 2
        assert await appointments_repo.count_waiting_before(db, doc["id"], today, live2_talon) == 2
        # Faqat jonli navbat: 1
        assert await appointments_repo.count_waiting_before(
            db, doc["id"], today, live2_talon, turi="LIVE"
        ) == 1


@pytest.mark.asyncio
async def test_queue_order_switches_at_slot_time(monkeypatch):
    """PROJECT_PLAN §3.5: slot vaqti kelgach slot bemori oldinga chiqadi, aks holda jonli birinchi."""
    from app.db.repositories import appointments_repo as ar

    class _FakeDateTime(datetime):
        _now = datetime(2026, 10, 20, 9, 0, 0)

        @classmethod
        def now(cls, tz=None):
            return cls._now

    monkeypatch.setattr(ar, "datetime", _FakeDateTime)

    async with get_db() as db:
        doctors = await doctors_repo.get_all_doctors(db)
        doc = doctors[0]
        sana = "2026-10-20"  # Seshanba — ish kuni (slot boshlanishi 15:00)

        slot_id, slot_talon = await appointments_repo.create_slot_appointment(
            db, doctor_id=doc["id"], sana=sana, slot_vaqti="15:20", bemor_ismi="Slot Bemor"
        )
        live_id, live_talon = await appointments_repo.create_live_appointment(
            db, doctor_id=doc["id"], sana=sana, bemor_ismi="Jonli Bemor"
        )
        # Slot oldindan yozilgani uchun past talon raqamiga ega
        assert slot_talon < live_talon

        # 09:00 (slot boshlanishidan oldin) — jonli bemor oldinda
        _FakeDateTime._now = datetime(2026, 10, 20, 9, 0, 0)
        order = await appointments_repo.get_today_queue_for_doctor(db, doc["id"], sana)
        relevant = [q for q in order if q["id"] in (slot_id, live_id)]
        assert relevant[0]["id"] == live_id

        # 15:30 — vaqti kelgan slot bemori birinchi o'ringa chiqadi
        _FakeDateTime._now = datetime(2026, 10, 20, 15, 30, 0)
        order2 = await appointments_repo.get_today_queue_for_doctor(db, doc["id"], sana)
        relevant2 = [q for q in order2 if q["id"] in (slot_id, live_id)]
        assert relevant2[0]["id"] == slot_id


@pytest.mark.asyncio
async def test_privacy_delete_user_data():
    async with get_db() as db:
        user = await users_repo.get_or_create_user(
            db, telegram_id=555666, ism="Privacy User", telefon="+998905556666"
        )
        fam_id = await users_repo.add_family_member(db, user["id"], "Child User")
        doctors = await doctors_repo.get_all_doctors(db)
        doc_id = doctors[0]["id"]

        app_id, _ = await appointments_repo.create_live_appointment(
            db, doctor_id=doc_id, sana="2026-10-21", user_id=user["id"], bemor_ismi="Privacy User"
        )
        await appointments_repo.add_to_waitlist(
            db, doctor_id=doc_id, sana="2026-10-21", user_id=user["id"], bemor_ismi="Privacy User"
        )

        # Delete user data (GDPR / Privacy)
        ok = await users_repo.delete_user_data(db, telegram_id=555666)
        assert ok is True

        # User is deleted
        u_deleted = await users_repo.get_user_by_telegram_id(db, 555666)
        assert u_deleted is None

        # Family members deleted
        fams = await users_repo.get_family_members(db, user["id"])
        assert len(fams) == 0

        # Appointment anonymized
        app_check = await appointments_repo.get_appointment_by_id(db, app_id)
        assert app_check["bemor_ismi"] == "Anonim Bemor"
        assert app_check["bemor_telefoni"] is None
        assert app_check["user_id"] is None


@pytest.mark.asyncio
async def test_live_queue_availability_ignores_slot_bookings(monkeypatch):
    """Slot bemorlari jonli navbat sig'imini to'ldirmasligi kerak.

    Aks holda kun oxiriga yaqin (masalan 14:00) 15:00 dagi slotlar hisobiga jonli
    navbat noto'g'ri "to'la" deb hisoblanardi.
    """
    fixed_dt = queue_service.tz.localize(datetime(2026, 10, 19, 14, 0))  # Dushanba, 14:00
    monkeypatch.setattr(queue_service, "get_current_datetime", lambda: fixed_dt)

    async with get_db() as db:
        doc = (await doctors_repo.get_all_doctors(db))[0]
        doc_id = doc["id"]
        sana = "2026-10-19"

        # 4 ta SLOT bemor (15:00–16:00) — jonli navbatga ta'sir qilmasligi kerak
        for i, t_val in enumerate(["15:00", "15:15", "15:30", "15:45"]):
            await appointments_repo.create_slot_appointment(
                db, doctor_id=doc_id, sana=sana, slot_vaqti=t_val, bemor_ismi=f"Slot {i}"
            )

        can_book, reason = await queue_service.check_live_queue_availability(db, doc_id)
        assert can_book is True, f"Slot bemorlari jonli navbatni to'sib qo'ydi: {reason}"

        # Endi jonli navbatni haqiqatan to'ldiramiz -> band bo'lishi kerak
        for i in range(20):
            await appointments_repo.create_live_appointment(
                db, doctor_id=doc_id, sana=sana, bemor_ismi=f"Jonli {i}"
            )
        can_book2, reason2 = await queue_service.check_live_queue_availability(db, doc_id)
        assert can_book2 is False
        assert reason2 == "doctor_card_live_full"


@pytest.mark.asyncio
async def test_confirm_appointment_records_timestamp():
    """Eslatma orqali tasdiqlash vaqtni saqlashi va faqat faol navbat uchun ishlashi kerak."""
    async with get_db() as db:
        doc = (await doctors_repo.get_all_doctors(db))[0]
        app_id, _ = await appointments_repo.create_slot_appointment(
            db, doctor_id=doc["id"], sana="2026-10-20", slot_vaqti="15:00", bemor_ismi="Ali"
        )

        assert await appointments_repo.confirm_appointment(db, app_id) is True
        app = await appointments_repo.get_appointment_by_id(db, app_id)
        assert app["tasdiqlangan_at"] is not None

        # Yakunlangandan keyin tasdiqlab bo'lmaydi
        await appointments_repo.set_appointment_status(db, app_id, "YAKUNLANDI")
        assert await appointments_repo.confirm_appointment(db, app_id) is False


@pytest.mark.asyncio
async def test_empty_specialties_hidden_from_bot_catalog():
    """Shifokori (botda ko'rinadigan) bo'lmagan mutaxassislik bot katalogida chiqmasligi kerak.

    Aks holda foydalanuvchi tugmani bosganda "faol shifokorlar mavjud emas"
    xabarini oladi va bot ishlamayotgan deb o'ylaydi.
    """
    async with get_db() as db:
        empty_id = await doctors_repo.create_specialty(db, "Kardiolog", "Кардиолог", 90)

        visible_ids = [s["id"] for s in await doctors_repo.get_specialties_with_visible_doctors(db)]
        assert empty_id not in visible_ids

        # Ko'rinadigan shifokor qo'shilsa — ro'yxatga kiradi
        await db.execute(
            "INSERT INTO doctors (specialty_id, ism_uz, ism_ru, xona, botda_korinadi, arxivlangan)"
            " VALUES (?, ?, ?, ?, 1, 0);",
            (empty_id, "Test Shifokor", "Тест Врач", "901"),
        )
        await db.commit()
        visible_ids2 = [s["id"] for s in await doctors_repo.get_specialties_with_visible_doctors(db)]
        assert empty_id in visible_ids2

        # `botda_korinadi=0` qilinsa — yana yashiriladi
        await db.execute("UPDATE doctors SET botda_korinadi = 0 WHERE specialty_id = ?;", (empty_id,))
        await db.commit()
        visible_ids3 = [s["id"] for s in await doctors_repo.get_specialties_with_visible_doctors(db)]
        assert empty_id not in visible_ids3
