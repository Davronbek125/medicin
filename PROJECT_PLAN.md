# 🏥 Klinika Navbat va Qabul Tizimi (Telegram Bot + WebApp)
## Texnik Topshiriq — Versiya 5.0 (Yakuniy)

> Bu yakuniy reja. Barcha ochiq savollar shunday klinika tizimlarida keng qo'llaniladigan yechimlar asosida yopildi (13-bo'limga qarang). Har qanday qarorni keyin o'zgartirish mumkin: barcha vaqtlar, limitlar va eslatmalar sozlamalar orqali boshqariladi, kodga tegish shart emas.
>
> **[v4]** belgisi v3.0 dan keyin qo'shilgan yoki tuzatilgan joylarni bildiradi.

---

## 1. Maqsad
Bitta klinika uchun navbatni raqamlashtirish:
* **Bemor** Telegram bot orqali shifokorni tanlaydi, jonli navbat yoki oldindan vaqt oladi, navbatini kuzatadi, eslatma oladi.
* **Xodimlar** Telegram WebApp (Mini App) orqali oqimni boshqaradi.
* To'lov, narxlar, kunlik son limiti, tanaffus — **loyiha doirasidan tashqarida**.

---

## 2. Rollar

| Rol | Kirish | Ko'radi / qiladi |
|---|---|---|
| 👑 Super Admin | Telegram WebApp + **login/parol** | Hammasi: shifokorlar, grafik, xodimlar, klinika ma'lumotlari, statistika |
| 🏢 Reception | Ruxsat berilgan Telegram hisob | Barcha shifokorlar navbati, joyida kelgan bemorni qo'shish, chaqirish/o'tkazish |
| 👨‍⚕️ Shifokor | Ruxsat berilgan Telegram hisob | Faqat o'z navbati: "Keyingi bemor", "Kelmadi", "Qabul tugadi" |
| 👤 Bemor | Ommaviy bot | Navbat olish, kuzatish, bekor qilish |

### 2.1. [v4] Xodimni tizimga ulash (Telegram ID ni qo'lda kiritmaslik uchun)
Telegram ID ni hech kim yoddan bilmaydi. Shuning uchun:
1. Super Admin "Xodim qo'shish" → rolni (Reception / Shifokor) va shifokor profilini tanlaydi.
2. Tizim **bir martalik taklif havolasi** yaratadi: `t.me/<bot>?start=inv_<token>` (24 soat amal qiladi).
3. Xodim havolani bosadi → bot uning Telegram hisobini rolga bog'laydi → token o'chadi.
4. Super Admin istalgan payt ruxsatni bekor qila oladi (xodim ishdan ketsa).

### 2.2. [v4] Super Admin uchun ikki qatlamli himoya
* Parol (`bcrypt`) **va** Telegram hisob (initData) birga tekshiriladi. Parol o'g'irlansa ham, begona Telegram hisobdan kirib bo'lmaydi.
* 5 ta xato urinishdan keyin 15 daqiqa blok.
* Sessiya tokeni 8 soat amal qiladi.
* Birinchi Super Admin `.env` faylidan yaratiladi, keyin parolni panelda almashtirish mumkin.

---

## 3. Ish vaqti va navbat qoidalari

### 3.1. Kun tuzilishi
| Vaqt | Nima bo'ladi |
|---|---|
| 08:00 | Bugungi jonli navbat ochiladi (bot orqali olish mumkin) |
| 10:00 – 15:00 | Jonli navbat qabuli |
| 15:00 – 16:00 | Oldindan yozilganlar (slotlar) |
| 16:00 | Qabul qilinmagan navbatlar yopiladi, bemorlarga xabar |
| 00:00 | Talon raqamlari #1 dan boshlanadi |

Vaqtlar **har bir shifokor uchun sozlanadi** (yuqoridagilar standart qiymat). Hammasi `Asia/Tashkent` vaqtida.

### 3.2. [v4] Taxminiy vaqt formulasi (tuzatildi)
v3.0 da formula `hozirgi vaqt` dan hisoblanardi. Ertalab 08:30 da navbat olgan bemor uchun bu xato natija beradi, chunki qabul 10:00 da boshlanadi.

```
boshlanish = max(hozirgi vaqt, jonli qabul boshlanishi)
taxminiy vaqt = boshlanish + (oldindagi kutayotganlar × o'rtacha qabul vaqti)
```
Bemorga aniq daqiqa emas, **oraliq** ko'rsatiladi: "~10:45 – 11:00".

### 3.3. [v4] Jonli navbatni yopish qoidasi
Jonli navbat ikki holatda avtomatik yopiladi (qaysi biri oldin bo'lsa):
* hisoblangan taxminiy vaqt jonli qabul tugashidan (15:00) oshsa;
* soat 14:30 bo'lsa.

Bemorga xabar: "Bugungi jonli navbat to'ldi. Oldindan yozilish yoki ertangi kun mavjud." va tegishli tugmalar.

### 3.4. [v4] Slotlar (tuzatildi)
v3.0 da slot qat'iy 15 daqiqa edi, lekin har bir shifokorning o'rtacha qabul vaqti boshqa. Endi:
* Slot uzunligi = shifokorning **o'rtacha qabul vaqti** (masalan, 20 daq → 15:00, 15:20, 15:40).
* Faqat shifokorning **ish kunlari** ko'rsatiladi; bayram va "qabul yo'q" kunlar chiqarib tashlanadi.
* Oldindan yozilish 7 kungacha. **Bugungi kun** uchun ham mumkin, agar slot vaqti hali o'tmagan bo'lsa.

### 3.5. Soat 15:00 dagi o'tish
* 15:00 dan keyin shifokor tablosida **vaqti kelgan slot bemori** birinchi o'ringa chiqadi.
* 15:00 gacha navbat olgan, lekin hali kirmagan jonli bemorlar **bekor qilinmaydi**. Ular slotlar orasidagi bo'sh oraliqlarda (slot bemori hali kelmagan yoki slot band qilinmagan bo'lsa) qabul qilinadi.
* Tablo shifokorga har doim bitta aniq "Keyingi bemor"ni ko'rsatadi. Shifokor kimni chaqirishni o'zi hisoblab o'tirmaydi.

### 3.6. Talon raqami
* Talon raqami (`#7`) o'zgarmaydi. Oldindagilar bekor qilsa, faqat "oldingizda N kishi" va vaqt kamayadi.
* Reception qo'shgan bemorlar ham **shu ketma-ketlikdan** raqam oladi (aralash raqamlar bo'lmasligi uchun).

### 3.7. [v4] Suiiste'molga qarshi (tuzatildi)
v3.0 da "bitta shifokorga 1 ta navbat" va "oila a'zolari uchun 3 ta" bir-biriga zid edi (ona ikki farzandini bitta pediatrga yozdira olmasdi). Endi:
* Cheklov **bemor (shaxs) bo'yicha**: bitta shaxs bitta shifokorda bir kunda faqat 1 ta faol navbat.
* Bitta Telegram hisobdan bir kunda ko'pi bilan **3 ta** faol navbat (o'zi + oila a'zolari).
* Oila a'zolari hisobga saqlanadi ("Mening yaqinlarim"), keyingi safar ism qayta yozilmaydi.
* Bot bo'yicha so'rovlar tezligi cheklanadi (anti-flood).
* Kontakt yuborilganda u **foydalanuvchining o'z raqami** ekanligi tekshiriladi (`contact.user_id == from_user.id`).

---

## 4. [v4] Hayotiy ssenariylar

| Vaziyat | Tizim nima qiladi |
|---|---|
| Bemor chaqirildi, lekin kelmadi | Shifokor "Kelmadi" bosadi → navbat `O'TKAZILDI` holatiga o'tadi, keyingi bemor chaqiriladi |
| O'tkazib yuborilgan bemor 10 daqiqa kechikib keldi | Reception/shifokor uni **"Qaytarish"** tugmasi bilan navbatga qaytaradi (keyingi o'ringa) |
| Bemor chaqirildi va kirdi | Shifokor "Qabul tugadi" bosmasa ham, "Keyingi bemor" bosilganda oldingi qabul avtomatik yakunlanadi |
| Shifokor "Keyingi"ni adashib 2 marta bosdi | Tugma 3 soniya nofaol bo'ladi + tasdiqlash oynasi |
| Shifokor kasal bo'lib qoldi | Super Admin "Bugun qabul yo'q" → bugungi barcha bemorlarga xabar, navbat yopiladi |
| Shifokor ta'tilga chiqdi | Super Admin sana oralig'ini belgilaydi → o'sha kunlarga yozilib bo'lmaydi, oldindan yozilganlarga xabar |
| Bayram kuni | Super Admin klinika bo'yicha dam olish kunini belgilaydi |
| Shifokor o'chirildi | Profil **arxivlanadi** (statistika yo'qolmasligi uchun), kelajakdagi navbatlar bekor qilinib, bemorlarga xabar boradi |
| Bemor botni bloklagan | Xabar yuborilmaydi, xato logga yoziladi, tizim ishlashda davom etadi |
| Telefoni yo'q bemor | Reception qo'shadi, qog'oz talonga raqam yoziladi, xabar yuborilmaydi |
| Bemor tilni almashtirmoqchi | Menyuda "🌐 Til" tugmasi |
| Bemor ro'yxatdan o'tmasdan menyuni bosdi | Avval ro'yxatdan o'tishga yo'naltiriladi |

---

## 5. Bildirishnomalar

| Qachon | Kimga | Matn (qisqa) |
|---|---|---|
| Navbat olinganda | Bemor | Talon: shifokor, xona, #raqam, oldingizda N kishi, ~vaqt |
| Oldida 2 kishi qolganda | Bemor | "Navbatingiz yaqin, kutish zalida bo'ling" |
| Chaqirilganda | Bemor | "Navbatingiz keldi! 204-xonaga kiring" |
| **[v4]** Slotdan 1 kun oldin (18:00) | Bemor | "Ertaga 15:20 da Dr. X qabuli. Bekor qilish / Tasdiqlash" |
| **[v4]** Slotdan 1 soat oldin | Bemor | "1 soatdan keyin qabulingiz" |
| Qabul bekor bo'lganda | Bemor | "Shifokor qabul qila olmaydi, uzr so'raymiz" |
| 16:00 da | Qabul qilinmaganlar | "Bugungi qabul yakunlandi, qayta yozilishingiz mumkin" |

Barcha xabarlar bemor tanlagan tilda (UZ/RU) yuboriladi. Ommaviy xabarlar Telegram limitiga mos ravishda (sekundiga ~25 ta) navbat bilan yuboriladi.

---

## 6. Bemor menyusi
1. 👨‍⚕️ Shifokorlar va qabul
2. 🎫 Mening navbatlarim
3. 👨‍👩‍👧 Mening yaqinlarim **[v4]**
4. 📍 Klinika haqida (manzil, lokatsiya, ish vaqti)
5. 📞 Aloqa
6. 🌐 Til

### 6.1. Shifokorni tanlash yo'li
```
👨‍⚕️ Shifokorlar va qabul
   └─ Yo'nalishlar ro'yxati (Terapevt, Kardiolog, Stomatolog...)
        └─ Shu yo'nalishdagi shifokorlar ro'yxati
             └─ Shifokor profili (kartochka)
                  └─ [🎫 Navbat olish]
```
Agar yo'nalishda bitta shifokor bo'lsa, ro'yxat o'tkazib yuborilib, to'g'ridan-to'g'ri uning profili ochiladi.

### 6.2. Shifokor profili (kartochka) ko'rinishi
Kartochka bitta xabar bo'lib keladi. Tartib yuqoridan pastga:

1. **Rasm** (ixtiyoriy). Rasm yuklanmagan bo'lsa, faqat matn ko'rinadi.
2. **Ma'lumotlar** (rasm ostida):

```text
👨‍⚕️ Dr. Jasur Aliyev
🩺 Kardiolog
🎓 Tajriba: 12 yil
📝 Oliy toifali shifokor. Yurak-qon tomir kasalliklari,
   EKG va qon bosimi muammolari bo'yicha mutaxassis.

🚪 Xona: 204
📅 Ish kunlari: Du, Chor, Juma
⏰ Jonli navbat: 10:00 – 15:00
📋 Oldindan yozilish: 15:00 – 16:00

🟢 Bugun qabul bor — oldingizda 4 kishi (~11:20)
```

3. **Tugmalar** (eng pastda):
   * `🎫 Navbat olish` — bosilganda: "Bugun (jonli navbat)" yoki "Oldindan yozilish (sana va vaqt)" tanlanadi, so'ng "Kim uchun?" (o'zim / yaqinim).
   * `⬅️ Orqaga` — shifokorlar ro'yxatiga qaytish.

**Holatga qarab o'zgarishlar:**
| Holat | Kartochkada nima ko'rinadi |
|---|---|
| Bugun qabul bor | 🟢 va hozirgi navbat holati, ikkala tugma faol |
| Jonli navbat to'lgan yoki yopilgan | 🟡 "Bugungi jonli navbat to'ldi", faqat "Oldindan yozilish" faol |
| Bugun ish kuni emas / qabul yo'q | 🔴 "Bugun qabul yo'q. Keyingi qabul: Chorshanba", faqat "Oldindan yozilish" faol |
| Shifokor ta'tilda | 🔴 "Ta'tilda (20-oktabrgacha)", navbat tugmasi yashiriladi |

### 6.3. Super Admin shifokor profilini boshqarishi
Super Admin WebApp'da har bir shifokor uchun:
* **Qo'shish:** ism, yo'nalish, xona, tajriba, tavsif (uz va ru), o'rtacha qabul vaqti, ish grafigi.
* **Rasm:** yuklash, almashtirish yoki o'chirish (ixtiyoriy). JPG/PNG, 5 MB gacha, avtomatik kvadrat shaklga keltiriladi.
* **Tahrirlash:** istalgan maydonni o'zgartirish. O'zgarish botda darhol ko'rinadi.
* **Botda ko'rsatish / yashirish:** shifokorni o'chirmasdan vaqtincha ro'yxatdan olib qo'yish.
* **O'chirish:** arxivlash (13-bo'lim, 16-qaror).
* **Ko'rinish tartibi:** ro'yxatdagi shifokorlar ketma-ketligini belgilash.
* **Oldindan ko'rish:** saqlashdan oldin kartochka botda qanday ko'rinishini ko'rish.

Yo'nalishlar (mutaxassisliklar) ham Super Admin tomonidan qo'shiladi, tahrirlanadi va o'chiriladi (uz va ru nomlari bilan).

---

## 7. Ma'lumotlar bazasi (To'liq va birlashtirilgan jadvallar)

| Jadval | Barcha maydonlar va tavsifi |
|---|---|
| `users` | `id`, `telegram_id` (UNIQUE), `ism`, `telefon`, `til` (uz/ru), `no_show_count` (standart: 0), `booking_blocked_until` (sana/vaqt), `consent_at` (rozilik vaqti), `yaratilgan_sana` |
| `family_members` | `id`, `user_id` (FK -> users), `ism`, `qarindoshlik` (farzand, ota-ona, turmush o'rtoq...), `yaratilgan_sana` |
| `staff` | `id`, `telegram_id` (UNIQUE), `rol` (SUPER_ADMIN, RECEPTION, DOCTOR), `doctor_id` (FK -> doctors, shifokor roli uchun), `faol` (1/0), `biriktirilgan_sana` |
| `invites` | `id`, `token` (UNIQUE), `rol`, `doctor_id`, `amal_muddati`, `ishlatilgan` (1/0) |
| `specialties` | `id`, `nomi_uz`, `nomi_ru`, `tartib` |
| `doctors` | `id`, `specialty_id` (FK), `ism_uz`, `ism_ru`, `xona`, `rasm_url` (ixtiyoriy), `tajriba_yili`, `tavsif_uz`, `tavsif_ru`, `ortacha_vaqt` (daqiqada, standart 15), `botda_korinadi` (1/0), `tartib`, `arxivlangan` (0/1) |
| `schedules` | `id`, `doctor_id` (FK), `hafta_kuni` (0-6), `jonli_boshlanish` (10:00), `jonli_tugash` (15:00), `slot_boshlanish` (15:00), `slot_tugash` (16:00), `faol` (1/0) |
| `days_off` | `id`, `doctor_id` (FK, NULL bo'lsa butun klinika), `sana`, `sabab` |
| `appointments` | `id`, `doctor_id` (FK), `sana`, `turi` ('LIVE' / 'SLOT'), `talon_raqami`, `slot_vaqti` (HH:MM yoki NULL), `bemor_ismi`, `bemor_telefoni`, `user_id` (FK, NULL bo'lsa joyida kelgan), `family_member_id` (FK, NULL bo'lsa o'zi), `holat` (`KUTMOQDA`, `CHAQIRILDI`, `YAKUNLANDI`, `OTKAZILDI`, `BEKOR`, `MUDDATI_OTDI`), `checked_in_at` (kelgan vaqti), `called_at`, `finished_at`, `yaratilgan_vaqt` |
| `waitlist` | `id`, `doctor_id` (FK), `sana`, `user_id` (FK), `bemor_ismi`, `tartib`, `taklif_yuborilgan_vaqt`, `holat` ('KUTMOQDA', 'TAKLIF_YUBORILDI', 'QABUL_QILINDI', 'MUDDATI_OTDI') |
| `clinic` | `id`, `nomi_uz`, `nomi_ru`, `manzil_uz`, `manzil_ru`, `lokatsiya_lat`, `lokatsiya_lon`, `telefonlar`, `ish_vaqti_uz`, `ish_vaqti_ru` |
| `audit_log` | `id`, `staff_id` (yoki telegram_id), `amal`, `obyekt`, `tafsilot`, `sana_vaqt` |

**Qat'iy cheklovlar va yaxlitlik (Integrity):**
* `UNIQUE(doctor_id, sana, talon_raqami)` — bitta kunda bitta shifokorga talon raqami hech qachon takrorlanmaydi.
* `UNIQUE(doctor_id, sana, slot_vaqti)` — faol slotlar uchun bitta vaqtga ikkita odam yozilishi mutlaqo imkonsiz.
* SQLite `WAL (Write-Ahead Logging)` rejimi — bir vaqtning o'zida yozish va o'qish operatsiyalari bloklanmaydi va yuqori tezlikda ishlaydi.
* **Check-in kafolati:** Agar bemor telefondan "Men klinikadaman"ni bosishni unutsa, Reception yoki Shifokor WebApp'da 1 ta tugma bilan uni kelgan deb belgilay oladi; agar zalda hali hech kim check-in qilmagan bo'lsa, shifokor oddiy talon ketma-ketligida ham chaqiraveradi (navbat hech qachon to'xtab qolmaydi).

---

## 8. Texnik arxitektura

| Qism | Texnologiya |
|---|---|
| Til | Python 3.11+ |
| Bot | aiogram 3.x |
| API + WebApp | FastAPI + uvicorn |
| Baza | SQLite (aiosqlite), **WAL rejimi** **[v4]** |
| Rejalashtiruvchi | APScheduler |
| Parol | bcrypt |
| Frontend | HTML + CSS + Vanilla JS, Telegram theme ranglari |
| Testlar | pytest, pytest-asyncio |

### 8.1. [v4] Jarayon modeli
* Bot va FastAPI **bitta jarayonda** ishlaydi (bitta event loop). Shifokor WebApp'da "Keyingi" bosganda API to'g'ridan-to'g'ri bot orqali bemorga xabar yuboradi.
* Bot ishlab chiqishda **polling**, serverda **webhook** rejimida ishlaydi.
* WebApp tablosi har 5 soniyada yangilanadi (polling). WebSocket keyingi versiyaga qoldiriladi.

### 8.2. Xavfsizlik
* Har bir WebApp API so'rovida `initData` HMAC-SHA256 bilan tekshiriladi va `auth_date` 24 soatdan eski bo'lmasligi kerak.
* Har bir endpoint rolni tekshiradi: shifokor faqat o'z `doctor_id` ma'lumotlarini oladi.
* Bot token, admin paroli, domen — faqat `.env` faylida. `.env` git'ga qo'shilmaydi.
* Barcha kiruvchi ma'lumotlar Pydantic sxemalari bilan tekshiriladi.
* HTML'da foydalanuvchi ma'lumotlari ekranlanadi (XSS himoyasi).
* Xodimlar amallari `audit_log` ga yoziladi.

### 8.3. [v4] Ishonchlilik
* Har kuni 23:59 da baza zaxira nusxasi, oxirgi 30 kunlik nusxa saqlanadi.
* Xatolar faylga loglanadi (aylanuvchi log fayllar).
* Server qayta ishga tushsa, rejalashtirilgan vazifalar va navbatlar holati bazadan tiklanadi.

---

## 9. [v4] Joylashtirish (Deploy)
* **Server:** O'zbekistondagi VPS (shaxsiy ma'lumotlarni mahalliy saqlash talabi uchun; yakuniy qarorni yurist bilan aniqlashtirish tavsiya etiladi).
* **Domen + HTTPS:** Telegram WebApp faqat HTTPS bilan ishlaydi (nginx + Let's Encrypt).
* **Avto-ishga tushish:** systemd xizmati.
* Ishlab chiqish paytida WebApp'ni sinash uchun vaqtinchalik HTTPS tunnel (masalan, ngrok yoki cloudflared).

---

## 10. Fayl tuzilmasi

```text
medicin/
├── app/
│   ├── bot/
│   │   ├── handlers/      # start, ro'yxat, shifokorlar, navbat, yaqinlar, til
│   │   ├── keyboards/
│   │   ├── middlewares/   # i18n, anti-flood, foydalanuvchini yuklash
│   │   └── states/
│   ├── web/
│   │   ├── api/           # auth, doctors, schedule, queue, staff, clinic, stats
│   │   ├── static/        # css, js
│   │   └── templates/     # super_admin, reception, doctor
│   ├── db/
│   │   ├── schema.sql
│   │   ├── connection.py
│   │   └── repositories/  # users, doctors, appointments, staff, clinic
│   ├── services/
│   │   ├── queue_service.py     # taxminiy vaqt, yopish qoidasi, talon
│   │   ├── slot_service.py      # slot generatsiyasi, ish kunlari, dam olish
│   │   ├── notification.py      # xabarlar, ommaviy yuborish
│   │   ├── auth_service.py      # initData, parol, taklif havolalari
│   │   └── scheduler.py         # 16:00, eslatmalar, backup
│   ├── locales/           # uz.json, ru.json
│   └── config.py
├── tests/
│   ├── unit/
│   └── integration/
├── backups/
├── logs/
├── .env.example
├── main.py
├── requirements.txt
└── PROJECT_PLAN.md
```

---

## 11. Bosqichlar

| № | Bosqich | Natija |
|---|---|---|
| 1 | Poydevor | Konfiguratsiya, baza sxemasi, repositoriylar, i18n, testlar muhiti |
| 2 | Navbat mantiqi | queue_service + slot_service (testlar bilan, chunki bu tizimning yuragi) |
| 3 | Bemor boti | Ro'yxat, shifokorlar, jonli navbat, slot, mening navbatlarim, yaqinlar, til |
| 4 | API va xavfsizlik | initData, Super Admin login, taklif havolalari, rol tekshiruvi |
| 5 | WebApp panellar | Super Admin, Reception, Shifokor |
| 6 | Bildirishnomalar va scheduler | Eslatmalar, 16:00 yopish, backup |
| 7 | Test va deploy | Ssenariylar bo'yicha test, serverga joylash |

---

## 12. Keyingi versiyalarga qoldirilganlar
* Qabuldan keyin baho/fikr qoldirish
* Tahlil natijalarini bot orqali yuborish
* Kutish zali uchun katta ekran (TV tablo)
* WebSocket orqali jonli yangilanish
* Bir nechta filial

---

## 13. Qabul qilingan qarorlar va sozlanadigan parametrlar

Quyidagi qarorlar ochiq savollarga berilgan tavsiya etilgan javoblar. Ularning hammasi Super Admin panelidagi sozlamalar yoki `.env` orqali o'zgartiriladi.

| № | Qaror | Standart qiymat | Sabab |
|---|---|---|---|
| 1 | Kelmay qolgan bemorni qaytarish | **Ha**, o'sha kuni, navbatdagi birinchi o'ringa | Bemor hojatxonada yoki dorixonada bo'lishi mumkin. Qaytadan navbat olishga majburlash adolatsiz |
| 2 | Slot eslatmalari | 1 kun oldin (18:00) va 1 soat oldin | Oldindan yozilganlarning kelmay qolishini sezilarli kamaytiradi |
| 3 | 1 kun oldingi eslatmada tasdiqlash | Bor. "Bekor qilish" bosilsa, slot boshqalarga ochiladi | Bo'sh qolgan slotni boshqa bemor egallaydi |
| 4 | 15:00 dan keyingi tartib | Slot bemori birinchi, qolgan jonli bemorlar bo'sh oraliqlarda | Oldindan yozilgan bemor va'da qilingan vaqtda kiradi, jonli bemor bekor qilinmaydi |
| 5 | Jonli navbat ochilishi | 08:00 | Kechasi navbatni band qilib qo'yishning oldini oladi |
| 6 | Jonli navbat yopilishi | 14:30 yoki taxminiy vaqt 15:00 dan oshganda | 15:00 dagi slotlar bilan to'qnashuvni yo'qotadi |
| 7 | Oldindan yozilish muddati | 7 kun | Uzoq muddatga band qilinganlar ko'pincha kelmay qoladi |
| 8 | Bekor qilish | Navbat chaqirilgunga qadar istalgan payt | Bemor uchun qulay, bo'shagan joy darhol boshqalarga o'tadi |
| 9 | Bitta hisobdan kunlik faol navbatlar | 3 ta | Oila uchun yetarli, suiiste'molni cheklaydi |
| 10 | Bitta shaxsga bitta shifokorda | Kuniga 1 ta | Takroriy talonlarning oldini oladi |
| 11 | "Yaqinlashdi" eslatmasi | Oldida 2 kishi qolganda | Bemor zalga yetib kelishga ulguradi |
| 12 | Tablo yangilanishi | Har 5 soniyada | Server yuklamasi va tezlik o'rtasidagi muvozanat |
| 13 | Xodim taklif havolasi muddati | 24 soat | Havola tarqalib ketsa ham xavf kichik |
| 14 | Super Admin blok | 5 xato urinish → 15 daqiqa | Parolni terib topishdan himoya |
| 15 | Zaxira nusxa | Har kuni 23:59, 30 kun saqlanadi | Bir oy ichidagi istalgan kunga qaytish mumkin |
| 16 | Shifokorni o'chirish | Arxivlash (to'liq o'chirmaslik) | Statistika va tarix saqlanadi |
| 17 | Bot tili | Birinchi kirishda tanlanadi, menyuda almashtiriladi | Ikki tilli auditoriya |

> **Eslatma:** Bu qarorlar shunday tizimlarda keng tarqalgan yechimlarga asoslangan, lekin aynan sizning klinikangizda sinovdan o'tmagan. Ishga tushgandan keyingi 1–2 hafta ichida bemorlar va xodimlar fikriga qarab limitlar va vaqtlarni sozlash tavsiya etiladi.

---

## 14. Jahon amaliyotidan olingan takomillashtirishlar

Navbat va onlayn yozilish tizimlarida (Doctolib, Zocdoc, Qminder, NHS kabi) keng qo'llaniladigan yechimlar. Har biri ikki guruhga ajratilgan: **birinchi versiyaga kiradi** va **keyinga qoldiriladi**, toki loyiha og'irlashib ketmasin.

### 14.1. Birinchi versiyaga kiradi

| № | Yechim | Qanday ishlaydi | Foydasi |
|---|---|---|---|
| 1 | **Klinikaga kelganini belgilash (check-in)** | Bemor klinikaga kelganda botda "✅ Men klinikadaman" tugmasini bosadi yoki reception belgilaydi. Shifokor tablosida kelganlar 🟢, kelmaganlar ⚪ bilan ko'rinadi | Shifokor uyda o'tirgan bemorni chaqirib vaqt yo'qotmaydi. Kelgan bemor ⚪ dagidan oldin chaqirilishi mumkin |
| 2 | **Haqiqiy qabul vaqtidan o'rganadigan hisob** | O'rtacha qabul vaqti qo'lda kiritilgan son emas, shifokorning so'nggi 30 ta qabulining haqiqiy davomiyligidan avtomatik hisoblanadi (qo'lda kiritilgan qiymat faqat boshlang'ich nuqta) | Taxminiy vaqt kundan-kunga aniqlashadi |
| 3 | **Bo'shagan slotga kutish ro'yxati** | Slotlar to'lgan bo'lsa, bemor "Joy bo'shasa xabar bering" tugmasini bosadi. Kimdir bekor qilsa, ro'yxatdagi birinchi bemorga 15 daqiqalik taklif boradi | Bekor qilingan slotlar bo'sh qolmaydi |
| 4 | **Kelmaslik hisobi (no-show)** | Bemor ketma-ket 3 marta kelmasa yoki bekor qilmasa, 14 kun davomida faqat jonli navbat olishi mumkin (oldindan yozilish yopiladi). Super Admin buni bekor qila oladi | Oldindan yozilib kelmaslik kamayadi. Jazo yumshoq va vaqtinchalik |
| 5 | **Eslatmada bir bosishda bekor qilish** | Har bir eslatmada "❌ Bekor qilish" tugmasi bor | Bemor qo'ng'iroq qilmasdan joyni bo'shatadi |
| 6 | **Rozilik va maxfiylik** | Ro'yxatdan o'tishda qisqa matn: qanday ma'lumot saqlanadi va nima uchun. Bemor "Roziman" bosadi. Menyuda "Ma'lumotlarimni o'chirish" | Shaxsiy ma'lumotlar qonunchiligiga muvofiqlik va ishonch |
| 7 | **Minimal ma'lumot tamoyili** | Faqat ism va telefon saqlanadi. Tashxis, shikoyat, tibbiy ma'lumot **saqlanmaydi** | Ma'lumot sizib chiqsa ham zarar minimal |
| 8 | **Asosiy ko'rsatkichlar (KPI)** | Super Admin panelida: o'rtacha kutish vaqti, kelmaslik foizi, shifokor bandligi, eng gavjum soatlar, bot va reception orqali kelganlar ulushi | Rahbar qarorni raqamlarga asoslab qabul qiladi |
| 9 | **Holat tekshiruvi (health check)** | `/health` manzili va bot ishlamay qolsa, Super Admin'ga Telegram xabari | Muammo bemorlardan oldin aniqlanadi |
| 10 | **Oddiy til va katta tugmalar** | Qisqa jumlalar, har bir qadamda "Orqaga" va "Bosh menyu", WebApp'da katta shrift va kontrast | Keksa bemorlar va shoshib turgan xodimlar uchun qulay |

**Check-in qo'shilgani sababli navbat tartibi aniqlashtiriladi:** "Keyingi bemor" bosilganda tizim talon tartibida birinchi **kelgan (🟢)** bemorni chaqiradi. Kelmagan bemorning talon raqami saqlanadi va u kelishi bilan navbatdagi o'rniga qaytadi.

### 14.2. Keyingi versiyalarga qoldiriladi

| Yechim | Nima uchun hozir emas |
|---|---|
| Kutish zalidagi TV tablo | Alohida ekran va qurilma kerak. Birinchi versiyada bot xabarlari yetarli |
| Ovozli chaqiruv ("14-raqam, 204-xona") | TV tablo bilan birga qilinadi |
| QR kod orqali check-in | Avval tugma orqali check-in sinab ko'riladi |
| Qabuldan keyin baho (NPS) | Avval asosiy oqim barqaror ishlashi kerak |
| SMS eslatmalar (Telegramsiz bemorlar uchun) | Pullik SMS xizmati kerak |
| Tibbiy axborot tizimi (MIS) bilan integratsiya | Klinikada bunday tizim bormi, noma'lum |
| WebSocket orqali jonli yangilanish | 5 soniyalik yangilanish bitta klinika uchun yetarli |

### 14.3. Ma'lumotlar bazasiga qo'shimchalar
| Jadval / maydon | Maqsad |
|---|---|
| `appointments.checked_in_at` | Bemor klinikaga kelgan vaqt |
| `appointments.called_at`, `finished_at` | Haqiqiy qabul davomiyligi va KPI uchun |
| `waitlist` | doctor_id, sana, user_id, bemor ismi, navbat tartibi, taklif yuborilgan vaqt |
| `users.no_show_count`, `users.booking_blocked_until` | Kelmaslik hisobi |
| `users.consent_at` | Rozilik berilgan vaqt |

### 14.4. Bosqichlarga ta'siri
* 2-bosqich (navbat mantig'i) ga: check-in, haqiqiy vaqtdan o'rganish, kutish ro'yxati, kelmaslik hisobi.
* 3-bosqich (bemor boti) ga: rozilik, "Men klinikadaman", ma'lumotlarni o'chirish.
* 5-bosqich (WebApp) ga: KPI paneli.
* 7-bosqich (deploy) ga: health check va ogohlantirishlar.
