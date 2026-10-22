"""
Rejali vazifalar (APScheduler) - 16:00 navbatni yopish, eslatmalar va 23:59 backup.
"""
import logging
from pathlib import Path
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
import aiosqlite
import pytz

from app.config import settings
from app.db.connection import get_db
from app.db.repositories import appointments_repo
from app.services import slot_service
from app.services.notification import send_notification
from app.services.i18n import t

logger = logging.getLogger(__name__)
tz = pytz.timezone(settings.TIMEZONE)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.TIMEZONE)

    # 1. Har kuni soat 16:00 da qabullarni yopish
    scheduler.add_job(
        expire_unattended_appointments,
        trigger="cron",
        hour=16,
        minute=0,
        args=[bot],
        id="daily_queue_close"
    )

    # 2. Har kuni soat 18:00 da ertangi slotlar haqida eslatma yuborish
    scheduler.add_job(
        send_tomorrow_reminders,
        trigger="cron",
        hour=18,
        minute=0,
        args=[bot],
        id="tomorrow_slot_reminders"
    )

    # 3. Har 10 daqiqada 1 soatdan keyingi slotlar haqida eslatma tekshiruvi
    scheduler.add_job(
        send_one_hour_slot_reminders,
        trigger="interval",
        minutes=10,
        args=[bot],
        id="one_hour_slot_reminders"
    )

    # 4. Har kuni soat 23:59 da ma'lumotlar bazasini arxivlash (Backup)
    scheduler.add_job(
        backup_database_job,
        trigger="cron",
        hour=23,
        minute=59,
        id="daily_db_backup"
    )

    # 5. Har 30 daqiqada tizim salomatligini tekshirish (Health monitor & Super Admin ogohlantirish)
    scheduler.add_job(
        periodic_health_monitor_job,
        trigger="interval",
        minutes=30,
        args=[bot],
        id="periodic_health_monitor"
    )

    # 6. Har 5 daqiqada muddati o'tgan kutish ro'yxati takliflarini yopish va keyingisiga o'tkazish
    scheduler.add_job(
        expire_waitlist_offers_job,
        trigger="interval",
        minutes=5,
        args=[bot],
        id="expire_waitlist_offers"
    )

    return scheduler


async def expire_waitlist_offers_job(bot: Bot):
    """Muddati o'tgan kutish ro'yxati takliflarini yopib, bo'shagan slotni keyingi nomzodga taklif qilish."""
    cutoff = (datetime.now(tz) - timedelta(minutes=settings.WAITLIST_OFFER_MINUTES)).isoformat()
    async with get_db() as db:
        expired = await appointments_repo.expire_stale_waitlist_offers(db, cutoff)

    for e in expired or []:
        logger.info(f"Kutish ro'yxati taklifi muddati tugadi: id={e['id']}")
        # Bo'shagan slot hali ham bo'sh bo'lsa — keyingi nomzodga taklif qilish
        if e.get("taklif_slot_vaqti"):
            await slot_service.offer_freed_slot(bot, e["doctor_id"], e["sana"], e["taklif_slot_vaqti"])


async def periodic_health_monitor_job(bot: Bot):
    """Vaqti-vaqti bilan ma'lumotlar bazasi va tizim salomatligini tekshirish."""
    try:
        async with get_db() as db:
            async with db.execute("SELECT 1;") as cur:
                await cur.fetchone()
    except Exception as e:
        logger.critical(f"HEALTH MONITOR ERROR: {e}")
        if settings.SUPER_ADMIN_TG_ID and bot:
            try:
                await bot.send_message(
                    settings.SUPER_ADMIN_TG_ID,
                    f"🚨 <b>DIQQAT: Tizim xatosi!</b>\nMa'lumotlar bazasida nosozlik aniqlandi: {e}"
                )
            except Exception:
                pass


async def expire_unattended_appointments(bot: Bot):
    """16:00 da kirmay qolgan navbatlarni yopish va xabar berish."""
    today_str = datetime.now(tz).strftime("%Y-%m-%d")
    async with get_db() as db:
        async with db.execute(
            """
            SELECT a.id, u.telegram_id, u.til
            FROM appointments a
            JOIN users u ON a.user_id = u.id
            WHERE a.sana = ? AND a.holat IN ('KUTMOQDA', 'CHAQIRILDI');
            """,
            (today_str,)
        ) as cur:
            patients = await cur.fetchall()

        expired_count = await appointments_repo.expire_day_appointments(db, today_str)

    logger.info(f"{today_str} uchun {expired_count} ta navbat EXPIRED qilindi.")

    for p in patients:
        tg_id = p["telegram_id"]
        lang = p["til"] or "uz"
        msg = t("notify_day_expired", lang)
        await send_notification(bot, tg_id, msg)


async def send_tomorrow_reminders(bot: Bot):
    """Ertangi slot egalariga tasdiqlash va bekor qilish tugmalari bilan eslatma yuborish."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    tomorrow_str = (datetime.now(tz) + timedelta(days=1)).strftime("%Y-%m-%d")

    async with get_db() as db:
        async with db.execute(
            """
            SELECT a.id, a.slot_vaqti, u.telegram_id, u.til, d.ism_uz, d.ism_ru, d.xona
            FROM appointments a
            JOIN users u ON a.user_id = u.id
            JOIN doctors d ON a.doctor_id = d.id
            WHERE a.sana = ? AND a.turi = 'SLOT' AND a.holat = 'KUTMOQDA';
            """,
            (tomorrow_str,)
        ) as cur:
            slots = await cur.fetchall()

    for s in slots:
        lang = s["til"] or "uz"
        doc_name = s["ism_ru"] if lang == "ru" else s["ism_uz"]
        msg = t("notify_slot_tomorrow", lang, time=s["slot_vaqti"], doctor_name=doc_name, room=s["xona"])
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="✅ " + ("Tasdiqlash" if lang == "uz" else "Подтвердить"), callback_data=f"confirm_{s['id']}"),
                InlineKeyboardButton(text="❌ " + ("Bekor qilish" if lang == "uz" else "Отменить"), callback_data=f"cancel_{s['id']}")
            ]]
        )
        await send_notification(bot, s["telegram_id"], msg, reply_markup=kb)


async def send_one_hour_slot_reminders(bot: Bot):
    """1 soatdan keyin boshlanadigan slot bemorlariga eslatma yuborish.

    Takroriy yuborishning oldini olish uchun `eslatma_1soat_at` ustuni ishlatiladi:
    eslatma yuborilgan navbat belgilanadi va keyingi siklda qayta tanlanmaydi.
    """
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    now_dt = datetime.now(tz)
    today_str = now_dt.strftime("%Y-%m-%d")

    async with get_db() as db:
        async with db.execute(
            """
            SELECT a.id, a.slot_vaqti, u.telegram_id, u.til, d.ism_uz, d.ism_ru, d.xona
            FROM appointments a
            JOIN users u ON a.user_id = u.id
            JOIN doctors d ON a.doctor_id = d.id
            WHERE a.sana = ? AND a.turi = 'SLOT' AND a.holat = 'KUTMOQDA'
              AND a.eslatma_1soat_at IS NULL;
            """,
            (today_str,)
        ) as cur:
            slots = await cur.fetchall()

    for s in slots:
        if not s["slot_vaqti"]:
            continue
        try:
            parts = s["slot_vaqti"].split(":")
            slot_time = now_dt.replace(hour=int(parts[0]), minute=int(parts[1]), second=0, microsecond=0)
            diff_mins = (slot_time - now_dt).total_seconds() / 60.0
            # Faqat bir marta yuborilishi uchun 10 daqiqalik tor oyna (job har 10 daqiqada ishlaydi)
            if 60 <= diff_mins < 70:
                lang = s["til"] or "uz"
                doc_name = s["ism_ru"] if lang == "ru" else s["ism_uz"]
                msg = t("notify_slot_one_hour", lang, time=s["slot_vaqti"], doctor_name=doc_name, room=s["xona"])
                kb = InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(text="❌ " + ("Bekor qilish" if lang == "uz" else "Отменить"), callback_data=f"cancel_{s['id']}")
                    ]]
                )
                if await send_notification(bot, s["telegram_id"], msg, reply_markup=kb):
                    async with get_db() as db:
                        await appointments_repo.mark_one_hour_reminder_sent(db, s["id"])
        except Exception as e:
            logger.error(f"Slot vaqtini tekshirishda xatolik: {e}")


async def backup_database_job():
    """WAL rejimidagi bazadan izchil (consistent) zaxira nusxa olish va 30 kundan eskilarni tozalash.

    Ilgari `shutil.copy2` bilan faqat asosiy `.db` fayl nusxalanardi. WAL rejimida hali
    checkpoint qilinmagan tranzaksiyalar `-wal` faylida qolib ketadi, natijada zaxira
    eskirgan yoki nomuvofiq bo'lishi mumkin edi. Endi SQLite'ning rasmiy online backup
    API'si ishlatiladi — u yozish-o'qish davom etayotganda ham izchil snapshot yaratadi
    va WAL mazmunini to'liq qamrab oladi.
    """
    src_db = Path(settings.DB_PATH)
    if not src_db.exists():
        return

    today_str = datetime.now(tz).strftime("%Y_%m_%d")
    backup_file = Path(settings.BACKUP_DIR) / f"clinic_{today_str}.db"

    try:
        Path(settings.BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        if backup_file.exists():
            backup_file.unlink()
        # SQLite'ning rasmiy online backup API'si (aiosqlite.Connection.backup) yozish
        # davom etayotganda ham izchil snapshot oladi va WAL mazmunini to'liq qamrab oladi.
        src = await aiosqlite.connect(str(src_db))
        try:
            dst = await aiosqlite.connect(str(backup_file))
            try:
                await src.backup(dst)
            finally:
                await dst.close()
        finally:
            await src.close()
        logger.info(f"Baza izchil zaxiralandi: {backup_file}")
    except Exception as e:
        logger.error(f"Zaxira nusxa olishda xatolik: {e}")
        return

    # 30 kundan eski nusxalarni tozalash
    try:
        threshold_dt = datetime.now(tz) - timedelta(days=30)
        for f in Path(settings.BACKUP_DIR).glob("clinic_*.db"):
            if f.stat().st_mtime < threshold_dt.timestamp():
                f.unlink(missing_ok=True)
    except Exception as e:
        logger.error(f"Eski zaxiralarni tozalashda xatolik: {e}")
