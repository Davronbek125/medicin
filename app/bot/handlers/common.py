"""
Telegram Bot - Umumiy buyruqlar va ro'yxatdan o'tish handlerlari.
"""
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext

from app.config import settings
from app.db.connection import get_db
from app.db.repositories import users_repo, clinic_repo, staff_repo
from app.services.i18n import t
from app.bot.states.patient_state import RegistrationState
from app.bot.keyboards.default import get_contact_keyboard, get_main_menu_keyboard
from app.bot.keyboards.inline import get_language_inline_keyboard, get_confirm_delete_data_keyboard

router = Router()


@router.message(Command("delete_my_data"))
async def cmd_delete_my_data(message: Message, lang: str):
    """Foydalanuvchiga shaxsiy ma'lumotlarini o'chirish imkonini berish (GDPR/Privacy)."""
    await _send_delete_data_confirm(message, lang)


async def _send_delete_data_confirm(message: Message, lang: str):
    await message.answer(
        t("delete_data_confirm", lang),
        reply_markup=get_confirm_delete_data_keyboard(lang)
    )


@router.message(F.text.in_([
    t("menu_delete_data", "uz"), t("menu_delete_data", "ru"),
    "🗑 Ma'lumotlarimni o'chirish", "🗑 Удалить мои данные"
]))
async def menu_delete_my_data(message: Message, user: dict, lang: str):
    """Asosiy menyudan shaxsiy ma'lumotlarni o'chirish."""
    if not user:
        await message.answer("Iltimos, avval /start buyrug'i orqali ro'yxatdan o'ting.")
        return
    await _send_delete_data_confirm(message, lang)


@router.callback_query(F.data == "confirm_delete_my_data")
async def cb_confirm_delete_my_data(callback: CallbackQuery, lang: str):
    async with get_db() as db:
        await users_repo.delete_user_data(db, callback.from_user.id)
    await callback.message.delete()
    await callback.message.answer(
        t("data_deleted_success", lang),
        reply_markup=ReplyKeyboardRemove()
    )


@router.callback_query(F.data == "cancel_delete_data")
async def cb_cancel_delete_data(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer("Bekor qilindi.")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user: dict, lang: str, is_staff: bool):
    # 1. Taklif havolasi bormi tekshirish (/start inv_xyz)
    args = message.text.split()[1:] if message.text else []
    if args and args[0].startswith("inv_"):
        token = args[0].replace("inv_", "")
        async with get_db() as db:
            redeemed = await staff_repo.redeem_invite(db, token, message.from_user.id)
            if redeemed:
                rol_nomi = "Qabulxona (Reception)" if redeemed["rol"] == "RECEPTION" else "Shifokor"
                await message.answer(
                    f"🎉 Tabriklaymiz! Siz <b>{rol_nomi}</b> sifatida tizimga muvaffaqiyatli ulandingiz.\n"
                    f"Boshqaruv panelini ochish uchun quyidagi menyudan foydalaning.",
                    reply_markup=get_main_menu_keyboard(lang, is_staff=True, webapp_url=settings.BASE_URL)
                )
                return
            else:
                await message.answer("⚠️ Ushbu taklif havolasi eskirgan yoki allaqachon ishlatilgan.")

    # 2. Agar foydalanuvchi ro'yxatdan o'tgan bo'lsa
    if user:
        async with get_db() as db:
            clinic = await clinic_repo.get_clinic_info(db)
        clinic_name = clinic.get(f"nomi_{lang}") if clinic else "Klinika"

        await message.answer(
            f"Assalomu alaykum, <b>{user['ism']}</b>!\n{clinic_name} botiga xush kelibsiz.",
            reply_markup=get_main_menu_keyboard(lang, is_staff=is_staff, webapp_url=settings.BASE_URL)
        )
        return

    # 3. Yangi foydalanuvchi - Til tanlash
    async with get_db() as db:
        clinic = await clinic_repo.get_clinic_info(db)
    clinic_name = clinic.get("nomi_uz") if clinic else "Klinika"

    await state.set_state(RegistrationState.waiting_for_lang)
    await message.answer(
        t("welcome", "uz", clinic_name=clinic_name),
        reply_markup=get_language_inline_keyboard()
    )


@router.callback_query(F.data.startswith("set_lang_"))
async def callback_set_language(callback: CallbackQuery, state: FSMContext, user: dict):
    new_lang = callback.data.replace("set_lang_", "")
    await callback.answer()

    if user:
        async with get_db() as db:
            await users_repo.update_user_language(db, callback.from_user.id, new_lang)
        await callback.message.delete()
        await callback.message.answer(
            t("lang_selected", new_lang),
            reply_markup=get_main_menu_keyboard(new_lang, webapp_url=settings.BASE_URL)
        )
        return

    # Ro'yxatdan o'tish davomi - telefon raqam so'rash
    await state.update_data(selected_lang=new_lang)
    await state.set_state(RegistrationState.waiting_for_contact)
    await callback.message.delete()
    await callback.message.answer(
        t("need_contact", new_lang),
        reply_markup=get_contact_keyboard(new_lang)
    )


@router.message(RegistrationState.waiting_for_contact, F.contact)
async def process_contact(message: Message, state: FSMContext):
    data = await state.get_data()
    selected_lang = data.get("selected_lang", "uz")

    # Anti-spoofing: Yuborilgan kontakt haqiqatda o'zinikimi?
    if message.contact.user_id != message.from_user.id:
        await message.answer(
            "⚠️ Iltimos, faqat o'zingizning shaxsiy raqamingizni yuboring!",
            reply_markup=get_contact_keyboard(selected_lang)
        )
        return

    phone = message.contact.phone_number
    if not phone.startswith("+"):
        phone = f"+{phone}"

    await state.update_data(phone=phone)
    await state.set_state(RegistrationState.waiting_for_name)

    await message.answer(
        t("contact_received", selected_lang) + "\n\n" + t("ask_name", selected_lang),
        reply_markup=ReplyKeyboardRemove()
    )


@router.message(RegistrationState.waiting_for_name, F.text)
async def process_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 3:
        await message.answer("Iltimos, to'liq ism-familiyangizni kiriting:")
        return

    data = await state.get_data()
    selected_lang = data.get("selected_lang", "uz")
    phone = data.get("phone", "")

    async with get_db() as db:
        await users_repo.get_or_create_user(
            db,
            telegram_id=message.from_user.id,
            ism=name,
            telefon=phone,
            til=selected_lang
        )

    await state.clear()
    await message.answer(
        t("registration_complete", selected_lang) + "\n\n" + t("privacy_consent", selected_lang),
        reply_markup=get_main_menu_keyboard(selected_lang, webapp_url=settings.BASE_URL)
    )


# --- Bosh menyu tugmalari ---

@router.message(F.text.in_([t("menu_lang", "uz"), t("menu_lang", "ru"), "🌐 Tilni o'zgartirish", "🌐 Сменить язык"]))
async def menu_change_language(message: Message, lang: str):
    await message.answer(
        t("welcome", lang, clinic_name="").split("\n\n")[-1],
        reply_markup=get_language_inline_keyboard()
    )


@router.message(F.text.in_([t("menu_about", "uz"), t("menu_about", "ru"), "📍 Klinika haqida", "📍 О клинике"]))
async def menu_about_clinic(message: Message, lang: str):
    async with get_db() as db:
        clinic = await clinic_repo.get_clinic_info(db)

    if not clinic:
        await message.answer("Klinika ma'lumotlari topilmadi.")
        return

    name = clinic.get(f"nomi_{lang}") or clinic.get("nomi_uz")
    address = clinic.get(f"manzil_{lang}") or clinic.get("manzil_uz")
    hours = clinic.get(f"ish_vaqti_{lang}") or clinic.get("ish_vaqti_uz")
    phones = clinic.get("telefonlar")

    text = (
        f"🏥 <b>{name}</b>\n\n"
        f"📍 <b>Manzil:</b> {address}\n"
        f"⏰ <b>Ish vaqti:</b> {hours}\n"
        f"📞 <b>Telefonlar:</b> {phones}\n"
    )
    await message.answer(text)

    # Lokatsiya yuborish
    lat = clinic.get("lokatsiya_lat")
    lon = clinic.get("lokatsiya_lon")
    if lat and lon:
        await message.answer_location(latitude=lat, longitude=lon)


@router.message(F.text.in_([t("menu_contact", "uz"), t("menu_contact", "ru"), "📞 Aloqa", "📞 Контакты"]))
async def menu_contact_clinic(message: Message, lang: str):
    async with get_db() as db:
        clinic = await clinic_repo.get_clinic_info(db)
    phones = clinic.get("telefonlar") if clinic else "+998 71 200 00 00"

    text = (
        f"📞 <b>Qabulxona (Reception) bilan bog'lanish:</b>\n\n"
        f"Telefon: <b>{phones}</b>\n\n"
        f"<i>Savollaringiz bo'lsa, bemalol qo'ng'iroq qilishingiz mumkin!</i>"
    )
    await message.answer(text)
