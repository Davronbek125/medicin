"""
Telegram Bot - Bemorlar uchun Shifokorlar katalogi, Navbat olish va Mening navbatim handlerlari.
"""
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.config import settings
from app.db.connection import get_db
from app.db.repositories import (
    doctors_repo, appointments_repo, users_repo, clinic_repo
)
from app.services import queue_service, slot_service
from app.services.i18n import t
from app.bot.states.patient_state import FamilyState, BookingFamilyState
from app.bot.keyboards.inline import (
    get_specialties_keyboard, get_doctors_keyboard, get_doctor_card_keyboard,
    get_booking_type_keyboard, get_person_choice_keyboard, get_dates_keyboard,
    get_slots_keyboard, get_ticket_keyboard, get_family_management_keyboard
)

router = Router()


async def _ensure_registered(target: "CallbackQuery | Message", user: dict, lang: str = "uz") -> bool:
    """Foydalanuvchi ro'yxatdan o'tganini tekshiradi. Bo'lmasa xabar berib False qaytaradi.

    Ro'yxatdan o'tmagan (yoki o'chirilgan) foydalanuvchi eski tugmani bosganda
    `user["id"]` da xatolik yuz bermasligi uchun markazlashgan himoya.
    """
    if user:
        return True
    txt = "Iltimos, avval /start buyrug'i orqali ro'yxatdan o'ting."
    if isinstance(target, CallbackQuery):
        await target.answer(txt, show_alert=True)
    else:
        await target.answer(txt)
    return False


# --- 1. Shifokorlar va qabul menyusi ---

@router.message(F.text.in_([t("menu_doctors", "uz"), t("menu_doctors", "ru"), "👨‍⚕️ Shifokorlar va qabul", "👨‍⚕️ Врачи и запись"]))
async def menu_doctors_catalog(message: Message, user: dict, lang: str):
    if not user:
        await message.answer("Iltimos, avval /start buyrug'i orqali ro'yxatdan o'ting.")
        return

    async with get_db() as db:
        specialties = await doctors_repo.get_specialties_with_visible_doctors(db)

    if not specialties:
        await message.answer(t("no_doctors", lang))
        return

    await message.answer(
        t("select_specialty", lang),
        reply_markup=get_specialties_keyboard(specialties, lang)
    )


@router.callback_query(F.data == "back_to_specs")
async def cb_back_to_specs(callback: CallbackQuery, lang: str):
    async with get_db() as db:
        specialties = await doctors_repo.get_specialties_with_visible_doctors(db)
    await callback.message.edit_text(
        t("select_specialty", lang),
        reply_markup=get_specialties_keyboard(specialties, lang)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("spec_"))
async def cb_select_specialty(callback: CallbackQuery, lang: str):
    specialty_id = int(callback.data.replace("spec_", ""))
    async with get_db() as db:
        doctors = await doctors_repo.get_doctors_by_specialty(db, specialty_id, only_visible=True)

    if not doctors:
        await callback.answer(t("no_doctors", lang), show_alert=True)
        return

    # Agar bitta shifokor bo'lsa, to'g'ridan-to'g'ri uning profili ochiladi
    if len(doctors) == 1:
        await show_doctor_card(callback.message, doctors[0]["id"], lang, edit=True)
        await callback.answer()
        return

    await callback.message.edit_text(
        t("select_doctor", lang),
        reply_markup=get_doctors_keyboard(doctors, lang)
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_doctors")
async def cb_back_to_doctors(callback: CallbackQuery, lang: str):
    # Mutaxassisliklar ro'yxatiga qaytish
    async with get_db() as db:
        specialties = await doctors_repo.get_specialties_with_visible_doctors(db)
    await callback.message.edit_text(
        t("select_specialty", lang),
        reply_markup=get_specialties_keyboard(specialties, lang)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("doc_"))
async def cb_select_doctor(callback: CallbackQuery, lang: str):
    doc_id = int(callback.data.replace("doc_", ""))
    await show_doctor_card(callback.message, doc_id, lang, edit=True)
    await callback.answer()


async def show_doctor_card(message: Message, doctor_id: int, lang: str, edit: bool = False):
    """Shifokor profil kartochkasini chiqarish."""
    async with get_db() as db:
        doc = await doctors_repo.get_doctor_by_id(db, doctor_id)
        if not doc:
            return

        can_book_live, live_reason = await queue_service.check_live_queue_availability(db, doctor_id)
        available_dates = await slot_service.get_available_booking_dates(db, doctor_id, days_ahead=7)
        can_book_slot = len(available_dates) > 0

        # Bugungi navbat holati matni
        today_str = queue_service.get_today_str()
        waiting_ahead = await appointments_repo.count_waiting_before(
            db, doctor_id, today_str, 999999, turi="LIVE"
        )
        _, eta_str = await queue_service.calculate_live_queue_eta(db, doctor_id, today_str, 999999)

        if can_book_live:
            status_text = t("doctor_card_today_open", lang, count=waiting_ahead, eta=eta_str)
        elif live_reason == "doctor_card_live_full":
            status_text = t("doctor_card_live_full", lang)
        else:
            status_text = t("doctor_card_no_reception", lang)

        # Bugungi ish vaqtini shifokor grafigidan olish (standart qiymatlar bilan zaxira)
        schedules = await doctors_repo.get_doctor_schedules(db, doctor_id)
        schedule = next(
            (s for s in schedules if s["hafta_kuni"] == datetime.now(queue_service.tz).weekday()),
            None
        ) or (schedules[0] if schedules else None)
        if schedule:
            live_hours = f"{schedule['jonli_boshlanish']} – {schedule['jonli_tugash']}"
            slot_hours = f"{schedule['slot_boshlanish']} – {schedule['slot_tugash']}"
        else:
            live_hours = "10:00 – 15:00"
            slot_hours = "15:00 – 16:00"

    name = doc.get(f"ism_{lang}") or doc.get("ism_uz")
    spec = doc.get(f"mutaxassislik_{lang}") or doc.get("mutaxassislik_uz") or "Mutaxassis"
    desc = doc.get(f"tavsif_{lang}") or doc.get("tavsif_uz") or ""
    room = doc.get("xona")
    exp = doc.get("tajriba_yili", 0)

    card_text = (
        f"👨‍⚕️ <b>{name}</b>\n"
        f"🩺 {spec}\n"
        f"🎓 <b>Tajriba:</b> {exp} yil\n"
        f"🚪 <b>Xona:</b> {room}-xona\n\n"
        f"📝 <i>{desc}</i>\n\n"
        f"⏰ <b>Jonli qabul:</b> {live_hours}\n"
        f"📋 <b>Oldindan slotlar:</b> {slot_hours}\n\n"
        f"{status_text}"
    )

    kb = get_doctor_card_keyboard(doctor_id, can_book_live, can_book_slot, lang)

    # Rasm bormi?
    photo_url = doc.get("rasm_url")
    if photo_url:
        try:
            if edit:
                await message.delete()
            await message.answer_photo(photo=photo_url, caption=card_text, reply_markup=kb)
            return
        except Exception:
            pass

    if edit:
        try:
            await message.edit_text(card_text, reply_markup=kb)
            return
        except Exception:
            await message.delete()
    await message.answer(card_text, reply_markup=kb)


# --- 2. Navbat olish oqimi ---

@router.callback_query(F.data.startswith("book_start_"))
async def cb_book_start(callback: CallbackQuery, lang: str):
    doc_id = int(callback.data.replace("book_start_", ""))
    async with get_db() as db:
        doc = await doctors_repo.get_doctor_by_id(db, doc_id)
        if not doc or doc.get("arxivlangan", 0):
            await callback.answer("Shifokor mavjud emas yoki arxivlangan.", show_alert=True)
            return
        can_live, _ = await queue_service.check_live_queue_availability(db, doc_id)
        dates = await slot_service.get_available_booking_dates(db, doc_id, days_ahead=7)
        can_slot = len(dates) > 0

    name = doc.get(f"ism_{lang}") or doc.get("ism_uz")
    spec = doc.get(f"mutaxassislik_{lang}") or doc.get("mutaxassislik_uz") or ""

    text = t("choose_booking_type", lang, doctor_name=name, specialty=spec)
    await callback.message.edit_text(
        text, reply_markup=get_booking_type_keyboard(doc_id, can_live, can_slot, lang)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("btype_live_"))
async def cb_choose_person_for_live(callback: CallbackQuery, user: dict, lang: str):
    if not await _ensure_registered(callback, user):
        return
    doc_id = int(callback.data.replace("btype_live_", ""))
    async with get_db() as db:
        family = await users_repo.get_family_members(db, user["id"])

    await callback.message.edit_text(
        t("choose_person", lang),
        reply_markup=get_person_choice_keyboard(doc_id, "live", "none", family, lang)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("btype_slot_"))
async def cb_choose_date_for_slot(callback: CallbackQuery, user: dict, lang: str):
    # Kelmaslik (No-show) blokini tekshirish
    if user and user.get("booking_blocked_until"):
        try:
            blocked_dt = datetime.fromisoformat(user["booking_blocked_until"])
            if datetime.now(queue_service.tz) < blocked_dt:
                await callback.answer(t("no_show_blocked", lang), show_alert=True)
                return
        except Exception:
            pass

    doc_id = int(callback.data.replace("btype_slot_", ""))
    async with get_db() as db:
        dates = await slot_service.get_available_booking_dates(db, doc_id, days_ahead=7)

    if not dates:
        await callback.answer("Hozircha bo'sh kunlar mavjud emas.", show_alert=True)
        return

    await callback.message.edit_text(
        "Qabul kunini tanlang:",
        reply_markup=get_dates_keyboard(doc_id, dates, lang)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("date_"))
async def cb_choose_slot_time(callback: CallbackQuery, lang: str):
    _, doc_id_str, sana = callback.data.split("_")
    doc_id = int(doc_id_str)

    async with get_db() as db:
        slots = await slot_service.get_available_slots_for_date(db, doc_id, sana)

    if not slots:
        await callback.answer("Tanlangan kunda qabul mavjud emas.", show_alert=True)
        return

    all_busy = not any(s["mavjud"] for s in slots)
    status_msg = "\n\n<i>Barcha slotlar band. Bo'sh joy paydo bo'lganda birinchi bo'lib xabar olishingiz mumkin:</i>" if all_busy else "\nBo'sh vaqt slotini tanlang:"

    await callback.message.edit_text(
        f"📅 Sana: <b>{sana}</b>{status_msg}",
        reply_markup=get_slots_keyboard(doc_id, sana, slots, lang)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("waitlist_join_"))
async def cb_join_waitlist(callback: CallbackQuery, user: dict, lang: str):
    if not await _ensure_registered(callback, user):
        return
    _, _, doc_id_str, sana = callback.data.split("_")
    doc_id = int(doc_id_str)
    async with get_db() as db:
        await appointments_repo.add_to_waitlist(db, doc_id, sana, user["id"], user["ism"])
    await callback.answer(t("waitlist_joined", lang), show_alert=True)


@router.callback_query(F.data == "slot_busy")
async def cb_slot_busy(callback: CallbackQuery):
    await callback.answer("Bu vaqt allaqachon band qilingan! Iltimos, boshqa vaqtni tanlang.", show_alert=True)


@router.callback_query(F.data.startswith("slot_"))
async def cb_choose_person_for_slot(callback: CallbackQuery, user: dict, lang: str):
    if not await _ensure_registered(callback, user):
        return
    _, doc_id_str, sana, time_val = callback.data.split("_")
    doc_id = int(doc_id_str)
    extra = f"{sana}T{time_val}"

    async with get_db() as db:
        family = await users_repo.get_family_members(db, user["id"])

    await callback.message.edit_text(
        t("choose_person", lang),
        reply_markup=get_person_choice_keyboard(doc_id, "slot", extra, family, lang)
    )
    await callback.answer()


# --- Yakuniy navbat yaratish ---

@router.callback_query(F.data.startswith("person_self_"))
async def cb_book_for_self(callback: CallbackQuery, user: dict, lang: str):
    if not await _ensure_registered(callback, user):
        return
    _, _, doc_id_str, btype, extra = callback.data.split("_")
    doc_id = int(doc_id_str)
    await finalize_booking(callback, user, doc_id, btype, extra, patient_name=user["ism"], family_id=None, lang=lang)


@router.callback_query(F.data.startswith("person_fam_"))
async def cb_book_for_family(callback: CallbackQuery, user: dict, lang: str):
    if not await _ensure_registered(callback, user):
        return
    _, _, fam_id_str, doc_id_str, btype, extra = callback.data.split("_")
    fam_id = int(fam_id_str)
    doc_id = int(doc_id_str)

    async with get_db() as db:
        members = await users_repo.get_family_members(db, user["id"])
        member = next((m for m in members if m["id"] == fam_id), None)

    # Ya'ni boshqa foydalanuvchining yaqin a'zosiga yozib qo'yishning oldini olish (IDOR)
    if not member:
        await callback.answer("Bu yaqin sizga tegishli emas.", show_alert=True)
        return

    await finalize_booking(callback, user, doc_id, btype, extra, patient_name=member["ism"], family_id=fam_id, lang=lang)


@router.callback_query(F.data.startswith("person_addfam_"))
async def cb_person_add_family(callback: CallbackQuery, state: FSMContext, lang: str):
    parts = callback.data.split("_")
    doc_id = int(parts[2])
    btype = parts[3]
    extra = parts[4]
    await state.update_data(booking_doc_id=doc_id, booking_btype=btype, booking_extra=extra)
    await state.set_state(BookingFamilyState.waiting_for_name)
    await callback.message.answer(t("enter_family_name", lang))
    await callback.answer()


@router.message(BookingFamilyState.waiting_for_name, F.text)
async def process_booking_family_name(message: Message, state: FSMContext, user: dict, lang: str):
    if not await _ensure_registered(message, user):
        await state.clear()
        return
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Iltimos, to'liq ismni kiriting:")
        return

    data = await state.get_data()
    doc_id = data.get("booking_doc_id")
    btype = data.get("booking_btype")
    extra = data.get("booking_extra")

    async with get_db() as db:
        fam_id = await users_repo.add_family_member(db, user["id"], name, qarindoshlik="Yaqini")

    await state.clear()
    await finalize_booking(message, user, doc_id, btype, extra, patient_name=name, family_id=fam_id, lang=lang)


async def finalize_booking(
    target: CallbackQuery | Message,
    user: dict,
    doctor_id: int,
    booking_type: str,
    extra: str,
    patient_name: str,
    family_id: int | None,
    lang: str
):
    if not await _ensure_registered(target, user):
        return
    is_cb = isinstance(target, CallbackQuery)
    today_str = queue_service.get_today_str()
    booking_date = today_str if booking_type == "live" else extra.split("T")[0]

    async with get_db() as db:
        # 1. Kunlik limit tekshiruvi (max 3)
        daily_cnt = await appointments_repo.count_user_daily_bookings(db, user["id"], booking_date)
        if daily_cnt >= settings.MAX_DAILY_PER_ACCOUNT:
            msg = t("daily_limit_reached", lang)
            if is_cb:
                await target.answer(msg, show_alert=True)
            else:
                await target.answer(msg)
            return

        # 2. Kelmaslik (No-show) blok tekshiruvi (jonli va slot — barcha turlar uchun)
        if user.get("booking_blocked_until"):
            try:
                blocked_dt = datetime.fromisoformat(user["booking_blocked_until"])
                if datetime.now(queue_service.tz) < blocked_dt:
                    msg = t("no_show_blocked", lang)
                    if is_cb:
                        await target.answer(msg, show_alert=True)
                    else:
                        await target.answer(msg)
                    return
            except Exception:
                pass

        # 3. Ayni shu shifokorga ayni shaxs (o'zi yoki tanlangan yaqin) faol navbat olganmi?
        has_active = await appointments_repo.check_user_active_booking(
            db, user["id"], doctor_id, booking_date, family_member_id=family_id
        )
        if has_active:
            msg = t("already_have_active_booking", lang)
            if is_cb:
                await target.answer(msg, show_alert=True)
            else:
                await target.answer(msg)
            return

        # 3. Yaratish
        clinic = await clinic_repo.get_clinic_info(db)
        clinic_name = clinic.get(f"nomi_{lang}") if clinic else "Klinika"

        if booking_type == "live":
            # Jonli navbat
            can_live, reason = await queue_service.check_live_queue_availability(db, doctor_id)
            if not can_live:
                msg = t(reason, lang)
                if is_cb:
                    await target.answer(msg, show_alert=True)
                else:
                    await target.answer(msg)
                return

            app_id, talon_raqami = await appointments_repo.create_live_appointment(
                db,
                doctor_id=doctor_id,
                sana=booking_date,
                bemor_ismi=patient_name,
                bemor_telefoni=user.get("telefon"),
                user_id=user["id"],
                family_member_id=family_id
            )
            ahead_count, eta_str = await queue_service.calculate_live_queue_eta(
                db, doctor_id, booking_date, talon_raqami
            )
            doc = await doctors_repo.get_doctor_by_id(db, doctor_id)

            ticket_text = t(
                "ticket_title", lang,
                clinic_name=clinic_name,
                doctor_name=doc.get(f"ism_{lang}") or doc.get("ism_uz"),
                specialty=doc.get(f"mutaxassislik_{lang}") or doc.get("mutaxassislik_uz"),
                room=doc.get("xona"),
                ticket_number=talon_raqami,
                ahead_count=ahead_count,
                eta=eta_str
            )
            if is_cb:
                await target.message.edit_text(
                    ticket_text, reply_markup=get_ticket_keyboard(app_id, is_checked_in=False, lang=lang)
                )
                await target.answer()
            else:
                await target.answer(
                    ticket_text, reply_markup=get_ticket_keyboard(app_id, is_checked_in=False, lang=lang)
                )

        else:
            # Slot yozilish
            slot_time = extra.split("T")[1]
            try:
                app_id, talon_raqami = await appointments_repo.create_slot_appointment(
                    db,
                    doctor_id=doctor_id,
                    sana=booking_date,
                    slot_vaqti=slot_time,
                    bemor_ismi=patient_name,
                    bemor_telefoni=user.get("telefon"),
                    user_id=user["id"],
                    family_member_id=family_id
                )
            except ValueError as e:
                msg = str(e)
                if is_cb:
                    await target.answer(msg, show_alert=True)
                else:
                    await target.answer(msg)
                return

            # Kutish ro'yxatidan kelgan nomzod bo'lsa, qabul qilingan deb belgilash
            await appointments_repo.mark_waitlist_accepted(db, user["id"], doctor_id, booking_date)

            doc = await doctors_repo.get_doctor_by_id(db, doctor_id)
            ticket_text = t(
                "slot_ticket_title", lang,
                clinic_name=clinic_name,
                doctor_name=doc.get(f"ism_{lang}") or doc.get("ism_uz"),
                specialty=doc.get(f"mutaxassislik_{lang}") or doc.get("mutaxassislik_uz"),
                room=doc.get("xona"),
                ticket_number=talon_raqami,
                date=booking_date,
                time=slot_time
            )
            if is_cb:
                await target.message.edit_text(
                    ticket_text, reply_markup=get_ticket_keyboard(app_id, is_checked_in=False, lang=lang)
                )
                await target.answer()
            else:
                await target.answer(
                    ticket_text, reply_markup=get_ticket_keyboard(app_id, is_checked_in=False, lang=lang)
                )


# --- 3. Mening navbatim va Boshqaruv tugmalari ---

@router.message(F.text.in_([t("menu_my_queue", "uz"), t("menu_my_queue", "ru"), "🎫 Mening navbatim", "🎫 Мои очереди"]))
async def menu_my_active_queues(message: Message, user: dict, lang: str):
    if not user:
        await message.answer("Iltimos, avval /start buyrug'i orqali ro'yxatdan o'ting.")
        return

    async with get_db() as db:
        apps = await appointments_repo.get_user_active_appointments(db, user["id"])
        clinic = await clinic_repo.get_clinic_info(db)
        clinic_name = clinic.get(f"nomi_{lang}") if clinic else "Klinika"

    if not apps:
        await message.answer(t("no_active_queue", lang))
        return

    for a in apps:
        doc_name = a.get(f"doctor_ism_{lang}") or a.get("doctor_ism_uz")
        spec_name = a.get(f"mutaxassislik_{lang}") or a.get("mutaxassislik_uz") or ""
        room = a.get("doctor_xona")

        if a["turi"] == "LIVE":
            ahead_count, eta_str = await queue_service.calculate_live_queue_eta(
                db, a["doctor_id"], a["sana"], a["talon_raqami"]
            )
            txt = t(
                "ticket_title", lang,
                clinic_name=clinic_name,
                doctor_name=doc_name,
                specialty=spec_name,
                room=room,
                ticket_number=a["talon_raqami"],
                ahead_count=ahead_count,
                eta=eta_str
            )
        else:
            txt = t(
                "slot_ticket_title", lang,
                clinic_name=clinic_name,
                doctor_name=doc_name,
                specialty=spec_name,
                room=room,
                ticket_number=a["talon_raqami"],
                date=a["sana"],
                time=a["slot_vaqti"]
            )

        is_checked = bool(a.get("checked_in_at"))
        await message.answer(txt, reply_markup=get_ticket_keyboard(a["id"], is_checked, lang))


@router.callback_query(F.data.startswith("checkin_"))
async def cb_check_in(callback: CallbackQuery, user: dict, lang: str):
    app_id = int(callback.data.replace("checkin_", ""))
    async with get_db() as db:
        app = await appointments_repo.get_appointment_by_id(db, app_id)
        if not app or not user or app.get("user_id") != user.get("id"):
            await callback.answer("Bu navbat sizga tegishli emas.", show_alert=True)
            return
        await appointments_repo.check_in_appointment(db, app_id)
    await callback.answer(t("check_in_success", lang), show_alert=True)
    # Tugmani qayta yangilash (Check-in tugmasi o'chadi)
    await callback.message.edit_reply_markup(
        reply_markup=get_ticket_keyboard(app_id, is_checked_in=True, lang=lang)
    )


@router.callback_query(F.data.startswith("cancel_"))
async def cb_cancel_appointment(callback: CallbackQuery, user: dict, lang: str):
    app_id = int(callback.data.replace("cancel_", ""))
    async with get_db() as db:
        app = await appointments_repo.get_appointment_by_id(db, app_id)
        if not app or not user or app.get("user_id") != user.get("id"):
            await callback.answer("Bu navbat sizga tegishli emas.", show_alert=True)
            return
        if app["holat"] not in ("KUTMOQDA", "CHAQIRILDI", "OTKAZILDI"):
            await callback.answer(
                "Bu navbatni bekor qilib bo'lmaydi (allaqachon yakunlangan yoki bekor qilingan).",
                show_alert=True
            )
            return
        await appointments_repo.cancel_appointment(db, app_id)

    # Slot bo'shagan bo'lsa, kutish ro'yxatidagi navbatdagi nomzodga taklif qilish
    if app.get("turi") == "SLOT":
        await slot_service.offer_freed_slot(callback.bot, app["doctor_id"], app["sana"], app["slot_vaqti"])

    await callback.answer(t("cancel_success", lang), show_alert=True)
    msg_txt = callback.message.text or ""
    await callback.message.edit_text(f"<s>{msg_txt}</s>\n\n❌ <b>Navbat bekor qilindi.</b>")


@router.callback_query(F.data.startswith("confirm_"))
async def cb_confirm_appointment(callback: CallbackQuery, user: dict, lang: str):
    app_id = int(callback.data.replace("confirm_", ""))
    async with get_db() as db:
        app = await appointments_repo.get_appointment_by_id(db, app_id)
        if not app or not user or app.get("user_id") != user.get("id"):
            await callback.answer("Bu navbat sizga tegishli emas.", show_alert=True)
            return
        if app.get("tasdiqlangan_at"):
            await callback.answer(t("confirm_success", lang), show_alert=True)
            return
        ok = await appointments_repo.confirm_appointment(db, app_id)

    if not ok:
        await callback.answer(
            "Bu navbatni tasdiqlab bo'lmaydi (yakunlangan yoki bekor qilingan).",
            show_alert=True
        )
        return

    await callback.answer(t("confirm_success", lang), show_alert=True)
    msg_txt = callback.message.text or ""
    await callback.message.edit_text(f"{msg_txt}\n\n✅ <b>Qabul tasdiqlandi.</b>")


@router.callback_query(F.data.startswith("refresh_"))
async def cb_refresh_ticket(callback: CallbackQuery, user: dict, lang: str):
    app_id = int(callback.data.replace("refresh_", ""))
    async with get_db() as db:
        a = await appointments_repo.get_appointment_by_id(db, app_id)
        if not a or not user or a.get("user_id") != user["id"]:
            await callback.answer("Bu navbat sizga tegishli emas.", show_alert=True)
            return
        if a["holat"] not in ("KUTMOQDA", "CHAQIRILDI"):
            await callback.answer("Navbat yakunlangan yoki bekor qilingan.", show_alert=True)
            return

        clinic = await clinic_repo.get_clinic_info(db)
        clinic_name = clinic.get(f"nomi_{lang}") if clinic else "Klinika"
        doc_name = a.get(f"doctor_ism_{lang}") or a.get("doctor_ism_uz")
        spec_name = a.get(f"mutaxassislik_{lang}") or a.get("mutaxassislik_uz") or ""
        room = a.get("doctor_xona")

        # Slot chiptasini yangilaganda jonli ETA emas, slot chiptasi ko'rsatiladi
        if a["turi"] == "LIVE":
            ahead_count, eta_str = await queue_service.calculate_live_queue_eta(
                db, a["doctor_id"], a["sana"], a["talon_raqami"]
            )
            txt = t(
                "ticket_title", lang,
                clinic_name=clinic_name,
                doctor_name=doc_name,
                specialty=spec_name,
                room=room,
                ticket_number=a["talon_raqami"],
                ahead_count=ahead_count,
                eta=eta_str
            )
        else:
            txt = t(
                "slot_ticket_title", lang,
                clinic_name=clinic_name,
                doctor_name=doc_name,
                specialty=spec_name,
                room=room,
                ticket_number=a["talon_raqami"],
                date=a["sana"],
                time=a["slot_vaqti"]
            )

    is_checked = bool(a.get("checked_in_at"))
    await callback.message.edit_text(txt, reply_markup=get_ticket_keyboard(a["id"], is_checked, lang))
    await callback.answer("Navbat holati yangilandi! ✅")


# --- 4. Mening yaqinlarim bo'limi ---

@router.message(F.text.in_([t("menu_family", "uz"), t("menu_family", "ru"), "👨‍👩‍👧 Mening yaqinlarim", "👨‍👩‍👧 Мои близкие"]))
async def menu_family_members(message: Message, user: dict, lang: str):
    if not user:
        await message.answer("Iltimos, avval /start buyrug'i orqali ro'yxatdan o'ting.")
        return

    async with get_db() as db:
        members = await users_repo.get_family_members(db, user["id"])

    if not members:
        txt = (
            "Sizda hali yaqinlaringiz ro'yxati shakllanmagan.\n\n"
            "Farzandingiz yoki ota-onangiz uchun oson navbat olish uchun ularni qo'shib qo'yishingiz mumkin."
        )
    else:
        txt = "👨‍👩‍👧 <b>Sizning yaqinlaringiz:</b>\n\n"
        for i, m in enumerate(members, 1):
            rel = f" ({m.get('qarindoshlik')})" if m.get("qarindoshlik") else ""
            txt += f"{i}. <b>{m['ism']}</b>{rel}\n"

    await message.answer(txt, reply_markup=get_family_management_keyboard(members, lang))


@router.callback_query(F.data.startswith("delfam_"))
async def cb_delete_family_member(callback: CallbackQuery, user: dict, lang: str):
    if not user:
        await callback.answer("Iltimos, avval /start orqali ro'yxatdan o'ting.", show_alert=True)
        return
    fam_id = int(callback.data.replace("delfam_", ""))
    async with get_db() as db:
        await users_repo.delete_family_member(db, fam_id, user["id"])
        members = await users_repo.get_family_members(db, user["id"])

    await callback.answer(t("family_deleted", lang), show_alert=True)
    if not members:
        txt = "Sizda hali yaqinlaringiz ro'yxati shakllanmagan."
    else:
        txt = "👨‍👩‍👧 <b>Sizning yaqinlaringiz:</b>\n\n"
        for i, m in enumerate(members, 1):
            rel = f" ({m.get('qarindoshlik')})" if m.get("qarindoshlik") else ""
            txt += f"{i}. <b>{m['ism']}</b>{rel}\n"

    await callback.message.edit_text(txt, reply_markup=get_family_management_keyboard(members, lang))


@router.callback_query(F.data == "add_fam_manual")
async def cb_add_family_manual(callback: CallbackQuery, state: FSMContext, user: dict, lang: str):
    if not user:
        await callback.answer("Iltimos, avval /start orqali ro'yxatdan o'ting.", show_alert=True)
        return
    await state.set_state(FamilyState.waiting_for_name)
    await callback.message.answer(t("enter_family_name", lang))
    await callback.answer()


@router.message(FamilyState.waiting_for_name, F.text)
async def process_family_name(message: Message, state: FSMContext, user: dict, lang: str):
    if not user:
        await state.clear()
        await message.answer("Iltimos, avval /start buyrug'i orqali ro'yxatdan o'ting.")
        return
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Iltimos, haqiqiy ismni kiriting:")
        return

    async with get_db() as db:
        await users_repo.add_family_member(db, user["id"], name, qarindoshlik="Yaqini")
        members = await users_repo.get_family_members(db, user["id"])

    await state.clear()
    await message.answer(
        f"✅ <b>{name}</b> yaqinlaringiz ro'yxatiga qo'shildi!",
        reply_markup=get_family_management_keyboard(members, lang)
    )
