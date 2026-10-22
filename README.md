# 🏥 Klinika Navbat Tizimi (Telegram Bot & WebApp)

Zamonaviy klinika uchun elektron navbat va qabul boshqaruvi tizimi (Python 3.11+, aiogram 3, FastAPI, SQLite WAL).

---

## 🚀 Tezkor Boshlash (Quick Start)

### 1. Virtual Muhitni faollashtirish
Loyihada virtual muhit (`venv`) allaqachon sozlangan va barcha kutubxonalar o'rnatilgan:
```powershell
.\venv\Scripts\activate
```

### 2. Sozlamalar (.env)
`.env` faylida o'zingizning Telegram Bot Tokeningizni kiriting:
```ini
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
SUPER_ADMIN_LOGIN=admin
SUPER_ADMIN_PASSWORD=admin12345
HOST=127.0.0.1
PORT=8000
```

### 3. Tizimni ishga tushirish
```powershell
.\venv\Scripts\python main.py
```
Tizim ishga tushgach, ham **Telegram Bot** polling rejimida, ham **FastAPI WebApp** serveri bitta jarayonda faoliyat ko'rsatadi.

---

## 📱 WebApp Panellari

Brauzerda yoki Telegram WebApp orqali quyidagi manzillarga kirish mumkin:

> ℹ️ `http://localhost:8000/` (root) — Telegram WebApp tugmasi shu manzilni ochadi. Sahifa foydalanuvchi rolini (`initData`) aniqlab, mos panelga yo'naltiradi: Shifokor → `/doctor`, Reception → `/reception`, Super Admin → `/admin`. Brauzerda (Telegram tashqarisida) ochilsa, panel tanlash havolalari ko'rsatiladi.

| Panel | Manzil | Tavsif |
|---|---|---|
| 👑 **Super Admin** | `http://localhost:8000/admin` | Login/Parol orqali kiriladi. Shifokorlar, grafiklar, xodimlar taklif havolalari va KPI analitika |
| 🏢 **Reception** | `http://localhost:8000/reception` | Barcha shifokorlar jonli navbati, joyida kelgan bemorga talon berish, chaqirish |
| 👨‍⚕️ **Shifokor Kabineti** | `http://localhost:8000/doctor` | Shifokor faqat o'z kabinetini ko'radi ("Keyingi bemor", "Kelmadi", "Qabul tugadi"). Super Admin/Reception boshqa shifokor kabinetini `?doctor_id=1` bilan ko'rishi mumkin |
| 🩺 **Salomatlik tekshiruvi** | `http://localhost:8000/health` | Tizim holati tekshiruvi |

---

## 🧪 Testlarni ishga tushirish
Barcha biznes mantiq, hisob-kitoblar va API integratsiyasini tekshirish uchun:
```powershell
.\venv\Scripts\pytest
```
Barcha 8 ta avtomatik test to'liq muvaffaqiyatli (Passed) o'tadi.

---

## 📂 Loyiha Tuzilmasi

```text
medicin/
├── app/
│   ├── bot/               # Telegram bot (aiogram 3)
│   │   ├── handlers/      # Umumiy va bemor handlerlari
│   │   ├── keyboards/     # Reply va Inline klaviaturalar
│   │   ├── middlewares/   # Foydalanuvchi va til middleware
│   │   └── states/        # FSM ro'yxatdan o'tish holatlari
│   ├── web/               # FastAPI WebApp & REST API
│   │   ├── api/           # Auth, Doctors, Queue, Staff, Clinic endpointlari
│   │   ├── static/        # CSS va dizayn uslublari
│   │   └── templates/     # SuperAdmin, Reception, Doctor HTML sahifalari
│   ├── db/                # Ma'lumotlar bazasi (SQLite WAL)
│   │   ├── schema.sql     # To'liq SQL sxemasi
│   │   ├── connection.py  # Asinxron ulanish
│   │   └── repositories/  # CRUD repo qatlamlari
│   ├── services/          # Navbat (ETA), Slotlar, i18n, Xabarlar va Scheduler
│   ├── locales/           # uz.json va ru.json
│   └── config.py          # Sozlamalar
├── tests/                 # Avtomatik testlar
├── main.py                # Asosiy ishga tushirish fayli
├── requirements.txt       # Kutubxonalar
└── PROJECT_PLAN.md        # To'liq texnik topshiriq (TZ v5.0)
```
