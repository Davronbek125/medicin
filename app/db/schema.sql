-- 🏥 Klinika Navbat Tizimi - SQLite Sxemasi (WAL rejimi)

PRAGMA foreign_keys = ON;

-- 1. Foydalanuvchilar (Bemorlar)
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    ism TEXT NOT NULL,
    telefon TEXT NOT NULL,
    til TEXT DEFAULT 'uz' CHECK (til IN ('uz', 'ru')),
    no_show_count INTEGER DEFAULT 0,
    booking_blocked_until TEXT,
    consent_at TEXT,
    yaratilgan_sana TEXT NOT NULL
);

-- 2. Oila a'zolari (Yaqinlarim)
CREATE TABLE IF NOT EXISTS family_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ism TEXT NOT NULL,
    qarindoshlik TEXT,
    yaratilgan_sana TEXT NOT NULL
);

-- 3. Mutaxassisliklar (Yo'nalishlar)
CREATE TABLE IF NOT EXISTS specialties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomi_uz TEXT NOT NULL,
    nomi_ru TEXT NOT NULL,
    tartib INTEGER DEFAULT 0
);

-- 4. Shifokorlar
CREATE TABLE IF NOT EXISTS doctors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    specialty_id INTEGER REFERENCES specialties(id) ON DELETE SET NULL,
    ism_uz TEXT NOT NULL,
    ism_ru TEXT NOT NULL,
    xona TEXT NOT NULL,
    rasm_url TEXT,
    tajriba_yili INTEGER DEFAULT 0,
    tavsif_uz TEXT,
    tavsif_ru TEXT,
    ortacha_vaqt INTEGER DEFAULT 15, -- daqiqada
    botda_korinadi INTEGER DEFAULT 1 CHECK (botda_korinadi IN (0, 1)),
    tartib INTEGER DEFAULT 0,
    arxivlangan INTEGER DEFAULT 0 CHECK (arxivlangan IN (0, 1))
);

-- 5. Xodimlar (Super Admin, Reception, Shifokor)
CREATE TABLE IF NOT EXISTS staff (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    rol TEXT NOT NULL CHECK (rol IN ('SUPER_ADMIN', 'RECEPTION', 'DOCTOR')),
    doctor_id INTEGER REFERENCES doctors(id) ON DELETE SET NULL,
    faol INTEGER DEFAULT 1 CHECK (faol IN (0, 1)),
    biriktirilgan_sana TEXT NOT NULL
);

-- 6. Bir martalik taklif havolalari (Xodimlarni ulash uchun)
CREATE TABLE IF NOT EXISTS invites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT UNIQUE NOT NULL,
    rol TEXT NOT NULL CHECK (rol IN ('RECEPTION', 'DOCTOR')),
    doctor_id INTEGER REFERENCES doctors(id) ON DELETE CASCADE,
    amal_muddati TEXT NOT NULL,
    ishlatilgan INTEGER DEFAULT 0 CHECK (ishlatilgan IN (0, 1))
);

-- 7. Shifokor ish grafigi (Hafta kunlari: 0=Dushanba, 6=Yakshanba)
CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id INTEGER NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    hafta_kuni INTEGER NOT NULL CHECK (hafta_kuni BETWEEN 0 AND 6),
    jonli_boshlanish TEXT DEFAULT '10:00',
    jonli_tugash TEXT DEFAULT '15:00',
    slot_boshlanish TEXT DEFAULT '15:00',
    slot_tugash TEXT DEFAULT '16:00',
    faol INTEGER DEFAULT 1 CHECK (faol IN (0, 1)),
    UNIQUE(doctor_id, hafta_kuni)
);

-- 8. Dam olish va ta'tillar
CREATE TABLE IF NOT EXISTS days_off (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id INTEGER REFERENCES doctors(id) ON DELETE CASCADE, -- NULL bo'lsa butun klinika
    sana TEXT NOT NULL, -- YYYY-MM-DD
    sabab TEXT
);

-- 9. Navbatlar va qabullar (Talonlar va slotlar)
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id INTEGER NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    sana TEXT NOT NULL, -- YYYY-MM-DD
    turi TEXT NOT NULL CHECK (turi IN ('LIVE', 'SLOT')),
    talon_raqami INTEGER NOT NULL,
    slot_vaqti TEXT, -- HH:MM yoki NULL
    bemor_ismi TEXT NOT NULL,
    bemor_telefoni TEXT,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    family_member_id INTEGER REFERENCES family_members(id) ON DELETE SET NULL,
    holat TEXT NOT NULL CHECK (holat IN ('KUTMOQDA', 'CHAQIRILDI', 'YAKUNLANDI', 'OTKAZILDI', 'BEKOR', 'MUDDATI_OTDI')),
    checked_in_at TEXT,
    called_at TEXT,
    finished_at TEXT,
    tasdiqlangan_at TEXT, -- eslatma orqali qabul tasdiqlangan vaqt (asosan SLOT)
    eslatma_1soat_at TEXT, -- "1 soatdan keyin" eslatmasi yuborilgan vaqt (takroriy yuborishning oldini oladi)
    yaratilgan_vaqt TEXT NOT NULL,
    UNIQUE(doctor_id, sana, talon_raqami)
);

-- 10. Kutish ro'yxati (Bo'shagan slotlar uchun)
CREATE TABLE IF NOT EXISTS waitlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id INTEGER NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    sana TEXT NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bemor_ismi TEXT NOT NULL,
    tartib INTEGER DEFAULT 0,
    taklif_yuborilgan_vaqt TEXT,
    taklif_slot_vaqti TEXT, -- taklif qilingan bo'shagan slot vaqti (HH:MM)
    holat TEXT DEFAULT 'KUTMOQDA' CHECK (holat IN ('KUTMOQDA', 'TAKLIF_YUBORILDI', 'QABUL_QILINDI', 'MUDDATI_OTDI'))
);

-- 11. Klinika ma'lumotlari
CREATE TABLE IF NOT EXISTS clinic (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomi_uz TEXT NOT NULL,
    nomi_ru TEXT NOT NULL,
    manzil_uz TEXT NOT NULL,
    manzil_ru TEXT NOT NULL,
    lokatsiya_lat REAL,
    lokatsiya_lon REAL,
    telefonlar TEXT NOT NULL,
    ish_vaqti_uz TEXT NOT NULL,
    ish_vaqti_ru TEXT NOT NULL
);

-- 12. Xodimlar amallari jurnali (Audit Log)
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id INTEGER,
    telegram_id INTEGER,
    amal TEXT NOT NULL,
    obyekt TEXT,
    tafsilot TEXT,
    sana_vaqt TEXT NOT NULL
);

-- 13. Super Admin xavfsizlik va bloklash
CREATE TABLE IF NOT EXISTS admin_security (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    login TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    failed_attempts INTEGER DEFAULT 0,
    blocked_until TEXT,
    oxirgi_kirish TEXT
);

-- Indekslar
CREATE INDEX IF NOT EXISTS idx_appointments_lookup ON appointments(doctor_id, sana, holat);
CREATE INDEX IF NOT EXISTS idx_appointments_user ON appointments(user_id, sana);
-- Slot bandligi faqat "haqiqiy" holatlarda hisobga olinadi (bekor/o'tkazib yuborilganlar joyni bo'shatadi).
-- Indeks qayta yaratiladi, chunki eski ta'rif OTKAZILDI holatini ham bloklab qo'yardi.
DROP INDEX IF EXISTS idx_appointments_active_slot;
CREATE UNIQUE INDEX IF NOT EXISTS idx_appointments_active_slot ON appointments(doctor_id, sana, slot_vaqti) WHERE slot_vaqti IS NOT NULL AND holat IN ('KUTMOQDA', 'CHAQIRILDI', 'YAKUNLANDI');
CREATE INDEX IF NOT EXISTS idx_schedules_doctor ON schedules(doctor_id, hafta_kuni);
CREATE INDEX IF NOT EXISTS idx_days_off_lookup ON days_off(sana, doctor_id);
CREATE INDEX IF NOT EXISTS idx_waitlist_lookup ON waitlist(doctor_id, sana, holat);
