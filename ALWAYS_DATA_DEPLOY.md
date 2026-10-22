# Alwaysdata.com Hostingida Loyihani Ishga Tushirish (Deploy) Qo'llanmasi

Ushbu qo'llanma **Klinika Navbat Tizimi**ni [admin.alwaysdata.com](https://admin.alwaysdata.com/) platformasida HTTPS domen, Telegram Webhook va avtomatik xizmat sifatida ishga tushirish bo'yicha bosqichma-bosqich ko'rsatmalarni o'z ichiga oladi.

---

## 1-Qadam: Alwaysdata hisobingizga kirish va SSH/SFTP orqali ulanish

1. [https://admin.alwaysdata.com/](https://admin.alwaysdata.com/) paneliga kiring.
2. Chap menyudan **Remote access** -> **SSH** bo'limiga o'ting va SSH parolini o'rnating yoki SSH kalitingizni qo'shing.
3. Terminal yoki Git Bash orqali serverga kiring:
   ```bash
   ssh hisob_nomingiz@ssh-hisob_nomingiz.alwaysdata.net
   ```

---

## 2-Qadam: Loyiha kodini yuklash

Serverdagi bosh katalogingizda (`/home/hisob_nomingiz/`) loyihani joylashtiring:

### A variant: Git orqali (Tavsiya qilinadi)
```bash
cd ~
git clone https://github.com/sizning_repo/medicin.git
cd medicin
```

### B variant: Web FTP / FileZilla orqali
1. Alwaysdata panelida **Files** bo'limiga kiring.
2. Kompyuteringizdagi loyiha fayllarini `/home/hisob_nomingiz/medicin/` katalogiga yuklang.

---

## 3-Qadam: Python virtual muhitini yaratish va kutubxonalarni o'rnatish

Alwaysdata terminalida loyiha papkasiga kiring:
```bash
cd ~/medicin

# Python 3.11 yoki 3.12 bilan virtualenv yaratish
python3 -m venv venv

# Kutubxonalarni o'rnatish
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
```

---

## 4-Qadam: Production sozlamalari (`.env`) ni tayyorlash

Namuna fayldan haqiqiy `.env` faylini yarating:
```bash
cp .env.production.example .env
nano .env
```

Quyidagi qiymatlarni o'zingizning haqiqiy ma'lumotlaringizga almashtiring:
1. `BOT_TOKEN`: `@BotFather` dan olgan haqiqiy bot tokeningiz.
2. `WEBHOOK_URL`: Alwaysdata dagi domeningiz (masalan: `https://shifomed.alwaysdata.net`). **Oxirida `/` bo'lmasligi kerak.**
3. `SUPER_ADMIN_PASSWORD`: Kuchli parol (masalan: `Klinika2026!Admin`).
4. `SUPER_ADMIN_TG_ID`: O'zingizning Telegram raqamli ID raqamingiz (buni `@userinfobot` orqali bilib olish mumkin).
5. `SECRET_KEY`: Kamida 32 ta harf va raqamdan iborat maxfiy kalit.
6. `ENVIRONMENT=production`.

Saqlash uchun: `Ctrl + O`, `Enter`, chiqish uchun: `Ctrl + X`.

---

## 5-Qadam: Alwaysdata Web panelida saytni sozlash

1. Chap menyudan **Web** -> **Sites** bo'limiga o'ting.
2. Mavjud standart saytni tahrirlang (yoki **Install an application** / **Add a site** bosing):
   - **Name**: `Klinika Navbat Tizimi`
   - **Domain**: `sizning-sayt.alwaysdata.net` (yoki o'zingizning shaxsiy domeningiz)
   - **Type**: **User program** tanlang.
   - **Command**:
     ```bash
     /home/hisob_nomingiz/medicin/venv/bin/uvicorn main:app --host :: --port $PORT --workers 1
     ```
     *(Eslatma: `hisob_nomingiz` o'rniga o'z Alwaysdata login nomingizni yozing)*
   - **Working directory**:
     ```bash
     /home/hisob_nomingiz/medicin
     ```
3. Sahifa pastidagi **Submit** tugmasini bosing.

---

## 6-Qadam: SSL (HTTPS) sertifikatini tekshirish

Alwaysdata barcha domenlarga avtomatik **Let's Encrypt** bepul SSL sertifikatini taqdim etadi:
1. **Web** -> **Sites** bo'limida saytingiz yonidagi sozlamalardan SSL faol ekanligini ko'ring (`Force SSL: Yes` qiling).
2. Brauzerda domeningizni oching: `https://sizning-sayt.alwaysdata.net/health`
3. Ekranda quyidagi javob chiqishi kerak:
   ```json
   {
     "status": "ok",
     "database": "connected",
     "bot_configured": true,
     "app": "Klinika Navbat Tizimi",
     "version": "1.0.0"
   }
   ```

---

## 7-Qadam: Telegram Webhook va Botni sinab ko'rish

Sayt ishga tushganda, tizim avtomatik tarzda Telegram Bot Webhook manzilini o'rnatadi:
`https://sizning-sayt.alwaysdata.net/api/bot/webhook`

Tekshirish:
1. Telegramda botingizga kiring va `/start` buyrug'ini bosing.
2. Bot til tanlash va bemor menyusini darhol chiqarishi kerak.
3. WebAdmin panelga kiring:
   `https://sizning-sayt.alwaysdata.net/admin`
4. `.env` da ko'rsatgan `admin` va parolingiz bilan tizimga kiring.

---

## 8-Qadam: Ma'lumotlar bazasi va zaxira nusxalar (Backup)

- SQLite bazasi: `/home/hisob_nomingiz/medicin/data/clinic.db`
- WAL fayllar avtomatik ishlaydi.
- Tizim ichida har kuni soat 23:00 da `backups/` papkasiga avtomatik zaxira olinadi.
- Alwaysdata ning o'zi ham har kuni server fayllarini zaxiralab boradi.
