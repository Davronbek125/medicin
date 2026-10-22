"""
Klinika Navbat Tizimi - Asosiy ishga tushirish fayli (FastAPI + aiogram 3).
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Update

from app.config import settings, validate_production_settings, warn_insecure_settings
from app.db.connection import init_db, get_db
from app.services.i18n import load_locales
from app.services.scheduler import setup_scheduler
from app.bot.middlewares.auth_middleware import UserAuthMiddleware
from app.bot.middlewares.anti_flood import AntiFloodMiddleware
from app.bot.handlers import common as common_handlers
from app.bot.handlers import patient as patient_handlers
from app.web.api import auth, doctors, queue, staff, clinic

# Logging sozlash
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "app" / "web" / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "web" / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Telegram Bot va Dispatcher
# Diqqat: aiogram Bot() konstruktori noto'g'ri tokenda ham xato bermaydi (validatsiya
# faqat so'rov yuborilganda bo'ladi), shuning uchun ortiqcha try/except kerak emas.
bot = Bot(
    token=settings.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

def setup_dispatcher() -> Dispatcher:
    """Dispatcher va routerlarni to'g'ri bog'lash."""
    dispatcher = Dispatcher()
    dispatcher.message.middleware(AntiFloodMiddleware(limit_seconds=0.4))
    dispatcher.callback_query.middleware(AntiFloodMiddleware(limit_seconds=0.4))
    dispatcher.message.middleware(UserAuthMiddleware())
    dispatcher.callback_query.middleware(UserAuthMiddleware())

    # Qayta yuklanganda (reload) xatolik bo'lmasligi uchun _parent_router ni tozalaymiz
    common_handlers.router._parent_router = None
    patient_handlers.router._parent_router = None

    dispatcher.include_router(common_handlers.router)
    dispatcher.include_router(patient_handlers.router)
    return dispatcher

dp = setup_dispatcher()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI va Bot hayotiy sikli (Lifespan)."""
    logger.info("🏥 Klinika Navbat Tizimi ishga tushmoqda...")
    
    validate_production_settings()

    # Ishlab chiqishda ham zaif (standart) sozlamalar haqida ogohlantiramiz
    for warning in warn_insecure_settings():
        logger.warning(f"🔐 Xavfsizlik ogohlantirishi: {warning}")

    # 1. Baza va i18n initsializatsiyasi
    await init_db()
    load_locales()
    app.state.bot = bot

    # 2. Rejali vazifalar (Scheduler)
    scheduler = setup_scheduler(bot)
    try:
        scheduler.start()
    except Exception as e:
        logger.warning(f"⚠️ Scheduler ishga tushirishda ogohlantirish: {e}")

    # 3. Botni ishga tushirish (Webhook yoki Polling)
    polling_task = None
    is_dummy = (
        not settings.BOT_TOKEN 
        or "dummy" in settings.BOT_TOKEN.lower() 
        or settings.BOT_TOKEN.startswith("123456789:")
    )
    webhook_mode = bool(
        settings.WEBHOOK_URL and settings.WEBHOOK_URL.startswith("https://")
    )

    if not is_dummy:
        # Bot username'ini avtomatik aniqlash (taklif havolalari to'g'ri bo'lishi uchun)
        try:
            me = await bot.get_me()
            if me and me.username:
                settings.BOT_USERNAME = me.username
                logger.info(f"🤖 Telegram bot aniqlandi: @{me.username}")
        except Exception as e:
            logger.warning(f"⚠️ Bot ma'lumotlarini olishda xatolik: {e}")

        if webhook_mode:
            webhook_endpoint = f"{settings.WEBHOOK_URL.rstrip('/')}/api/bot/webhook"
            secret_token = settings.SECRET_KEY[:32]
            try:
                logger.info(f"🌐 Alwaysdata/Production Webhook o'rnatilmoqda: {webhook_endpoint}")
                await bot.set_webhook(
                    url=webhook_endpoint,
                    secret_token=secret_token,
                    # False: ilova uxlab qolgan (idle stop) yoki qayta ishga tushayotganda
                    # kelib qolgan xabarlar yo'qolmasin — ular keyin navbat bilan ishlanadi.
                    drop_pending_updates=False,
                    allowed_updates=dp.resolve_used_update_types()
                )
            except Exception as e:
                logger.error(f"❌ Webhook o'rnatishda xatolik: {e}")
        else:
            async def safe_polling():
                try:
                    logger.info("🤖 Telegram bot polling rejimida boshlanmoqda...")
                    await dp.start_polling(bot)
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"❌ Telegram bot ulanish xatosi: {e}")
                    logger.warning("⚠️ WebApp ishlashda davom etadi. Bot tokenini @BotFather orqali tekshiring.")

            polling_task = asyncio.create_task(safe_polling())
    else:
        logger.warning("⚠️ BOT_TOKEN o'rnatilmagan yoki dummy. Telegram bot kutish rejimida, WebApp to'liq ishlaydi.")

    yield

    # To'xtatish
    logger.info("🛑 Tizim to'xtatilmoqda...")
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass
    if not is_dummy and webhook_mode:
        try:
            await bot.delete_webhook()
        except Exception:
            pass
    if polling_task and not polling_task.done():
        polling_task.cancel()
    try:
        await bot.session.close()
    except Exception:
        pass


# FastAPI dasturi
app = FastAPI(
    title="Klinika Navbat Tizimi API & WebApp",
    version="1.0.0",
    lifespan=lifespan
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response

# Statik fayllar
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# API Routerni ulash
app.include_router(auth.router)
app.include_router(doctors.router)
app.include_router(queue.router)
app.include_router(staff.router)
app.include_router(clinic.router)


@app.post("/api/bot/webhook")
async def telegram_webhook(request: Request):
    """Alwaysdata / Production Telegram webhook endpoint."""
    secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    expected_secret = settings.SECRET_KEY[:32]
    if secret_header != expected_secret:
        return JSONResponse(status_code=403, content={"error": "Invalid secret token"})
    
    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Webhook update processing error: {e}")
        return JSONResponse(status_code=500, content={"error": "Update processing failed"})


# --- WebApp Sahifalari ---

@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    # Root manzil — Telegram WebApp tugmasi shu yerga olib keladi. Sahifa foydalanuvchi
    # rolini (initData orqali) aniqlab, mos panelga yo'naltiradi: Doctor -> /doctor,
    # Reception -> /reception, Super Admin -> /admin.
    return templates.TemplateResponse(request=request, name="panel.html")


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse(request=request, name="super_admin.html")


@app.get("/reception", response_class=HTMLResponse)
async def reception_page(request: Request):
    return templates.TemplateResponse(request=request, name="reception.html")


@app.get("/doctor", response_class=HTMLResponse)
async def doctor_page(request: Request):
    return templates.TemplateResponse(request=request, name="doctor.html")


@app.get("/health")
async def health_check():
    db_status = "connected"
    try:
        async with get_db() as db:
            async with db.execute("SELECT 1;") as cursor:
                await cursor.fetchone()
    except Exception as e:
        logger.error(f"Health check DB error: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": "disconnected"}
        )

    bot_configured = bool(
        settings.BOT_TOKEN
        and "dummy" not in settings.BOT_TOKEN.lower()
        and not settings.BOT_TOKEN.startswith("123456789:")
    )

    return {
        "status": "ok",
        "database": db_status,
        "bot_configured": bot_configured,
        "app": "Klinika Navbat Tizimi",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT
    )
