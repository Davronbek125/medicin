"""
Klinika Navbat Tizimi - Asinxron SQLite ma'lumotlar bazasi ulanishi.
"""
from contextlib import asynccontextmanager
from pathlib import Path
import aiosqlite
import bcrypt
from app.config import settings

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


@asynccontextmanager
async def get_db():
    """Ma'lumotlar bazasiga xavfsiz ulanish va tranzaksiya boshqaruvi."""
    db = await aiosqlite.connect(settings.DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode = WAL;")
    await db.execute("PRAGMA foreign_keys = ON;")
    await db.execute("PRAGMA synchronous = NORMAL;")
    await db.execute("PRAGMA busy_timeout = 5000;")
    try:
        yield db
    finally:
        await db.close()


async def init_db() -> None:
    """Ma'lumotlar bazasini initsializatsiya qilish va boshlang'ich ma'lumotlarni kiritish."""
    async with get_db() as db:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            await db.executescript(f.read())

        # --- Migratsiyalar (eski bazalar uchun) ---
        # waitlist.taklif_slot_vaqti ustuni (kutish ro'yxati taklifida slot vaqtini eslab qolish uchun)
        async with db.execute("PRAGMA table_info(waitlist);") as cur:
            waitlist_cols = {row["name"] for row in await cur.fetchall()}
        if "taklif_slot_vaqti" not in waitlist_cols:
            await db.execute("ALTER TABLE waitlist ADD COLUMN taklif_slot_vaqti TEXT;")

        # appointments.tasdiqlangan_at ustuni (eslatma orqali qabul tasdiqlanganini qayd qilish uchun)
        async with db.execute("PRAGMA table_info(appointments);") as cur:
            appt_cols = {row["name"] for row in await cur.fetchall()}
        if "tasdiqlangan_at" not in appt_cols:
            await db.execute("ALTER TABLE appointments ADD COLUMN tasdiqlangan_at TEXT;")

        # appointments.eslatma_1soat_at ustuni ("1 soatdan keyin" eslatmasi yuborilganini qayd qilish)
        if "eslatma_1soat_at" not in appt_cols:
            await db.execute("ALTER TABLE appointments ADD COLUMN eslatma_1soat_at TEXT;")

        # Boshlang'ich Klinika ma'lumotlarini tekshirish
        async with db.execute("SELECT id FROM clinic LIMIT 1;") as cursor:
            clinic = await cursor.fetchone()
            if not clinic:
                await db.execute(
                    """
                    INSERT INTO clinic (
                        nomi_uz, nomi_ru, manzil_uz, manzil_ru,
                        lokatsiya_lat, lokatsiya_lon, telefonlar,
                        ish_vaqti_uz, ish_vaqti_ru
                    ) VALUES (
                        'Shifo Med Klinikasi', 'Клиника Shifo Med',
                        'Toshkent sh., Chilonzor tumani, Bunyodkor shoh ko‘chasi, 12-uy',
                        'г. Ташкент, Чиланзарский район, проспект Бунёдкор, дом 12',
                        41.2858, 69.2038,
                        '+998 71 200 00 00, +998 90 123 45 67',
                        'Dushanba - Shanba: 08:00 - 18:00',
                        'Понедельник - Суббота: 08:00 - 18:00'
                    );
                    """
                )
        
        # Boshlang'ich Super Admin ma'lumotlarini tekshirish
        async with db.execute("SELECT id FROM admin_security WHERE login = ?;", (settings.SUPER_ADMIN_LOGIN,)) as cursor:
            admin = await cursor.fetchone()
            if not admin:
                pwd_bytes = settings.SUPER_ADMIN_PASSWORD.encode("utf-8")[:72]
                pwd_hash = bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")
                await db.execute(
                    """
                    INSERT INTO admin_security (login, password_hash)
                    VALUES (?, ?);
                    """,
                    (settings.SUPER_ADMIN_LOGIN, pwd_hash)
                )

        # Telegram Super Admin ID biriktirish
        if settings.SUPER_ADMIN_TG_ID and settings.SUPER_ADMIN_TG_ID > 0:
            from datetime import datetime
            now_iso = datetime.now().isoformat()
            await db.execute(
                """
                INSERT INTO staff (telegram_id, rol, faol, biriktirilgan_sana)
                VALUES (?, 'SUPER_ADMIN', 1, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET rol = 'SUPER_ADMIN', faol = 1;
                """,
                (settings.SUPER_ADMIN_TG_ID, now_iso)
            )

        # Boshlang'ich mutaxassisliklar va shifokorlar (namuna sifatida, agar bo'sh bo'lsa)
        async with db.execute("SELECT id FROM specialties LIMIT 1;") as cursor:
            spec = await cursor.fetchone()
            if not spec:
                await db.execute(
                    "INSERT INTO specialties (nomi_uz, nomi_ru, tartib) VALUES ('Terapevt', 'Терапевт', 1);"
                )
                await db.execute(
                    "INSERT INTO specialties (nomi_uz, nomi_ru, tartib) VALUES ('Kardiolog', 'Кардиолог', 2);"
                )
                await db.execute(
                    "INSERT INTO specialties (nomi_uz, nomi_ru, tartib) VALUES ('Pediatr', 'Педиатр', 3);"
                )
                
                # Namuna shifokor
                cursor_spec = await db.execute("SELECT id FROM specialties WHERE nomi_uz = 'Terapevt' LIMIT 1;")
                terapevt_row = await cursor_spec.fetchone()
                if terapevt_row:
                    await db.execute(
                        """
                        INSERT INTO doctors (
                            specialty_id, ism_uz, ism_ru, xona, tajriba_yili,
                            tavsif_uz, tavsif_ru, ortacha_vaqt, botda_korinadi, tartib
                        ) VALUES (
                            ?, 'Dr. Jasur Aliyev', 'Др. Джасур Алиев', '204', 10,
                            'Oliy toifali terapevt. Umumiy ko‘rik va diagnostika bo‘yicha mutaxassis.',
                            'Терапевт высшей категории. Специалист по общей диагностике.',
                            15, 1, 1
                        );
                        """,
                        (terapevt_row["id"],)
                    )
                    # Ish grafigi (Du-Sha: 0, 1, 2, 3, 4, 5)
                    cursor_doc = await db.execute("SELECT id FROM doctors LIMIT 1;")
                    doc_row = await cursor_doc.fetchone()
                    if doc_row:
                        for day in range(6):  # 0 to 5 (Du-Sha)
                            await db.execute(
                                """
                                INSERT OR IGNORE INTO schedules (doctor_id, hafta_kuni, jonli_boshlanish, jonli_tugash, slot_boshlanish, slot_tugash)
                                VALUES (?, ?, '10:00', '15:00', '15:00', '16:00');
                                """,
                                (doc_row["id"], day)
                            )

        await db.commit()
