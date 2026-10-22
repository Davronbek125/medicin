"""
Klinika Navbat Tizimi - Asosiy konfiguratsiya moduli.
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Telegram Bot
    BOT_TOKEN: str = Field(default="dummy_token_replace_with_real_token")
    BOT_USERNAME: str = Field(default="")
    WEBHOOK_URL: str = Field(default="")
    
    # Server
    HOST: str = Field(default="127.0.0.1")
    PORT: int = Field(default=8000)
    BASE_URL: str = Field(default="http://localhost:8000")
    ENVIRONMENT: str = Field(default="development")
    
    # Super Admin
    SUPER_ADMIN_LOGIN: str = Field(default="admin")
    SUPER_ADMIN_PASSWORD: str = Field(default="admin12345")
    SUPER_ADMIN_TG_ID: int = Field(default=0)
    
    # Security
    SECRET_KEY: str = Field(default="super-secret-clinic-key-change-in-production-32chars")
    ACCESS_TOKEN_EXPIRE_HOURS: int = Field(default=8)
    MAX_LOGIN_ATTEMPTS: int = Field(default=5)
    LOCKOUT_MINUTES: int = Field(default=15)
    
    # Timezone & Storage
    TIMEZONE: str = Field(default="Asia/Tashkent")
    DB_PATH: str = Field(default=str(BASE_DIR / "data" / "clinic.db"))
    BACKUP_DIR: str = Field(default=str(BASE_DIR / "backups"))
    LOGS_DIR: str = Field(default=str(BASE_DIR / "logs"))
    
    # Navbat qoidalari (Sozlanadigan parametrlar)
    LIVE_QUEUE_OPEN_TIME: str = Field(default="08:00")
    LIVE_QUEUE_CUTOFF_TIME: str = Field(default="14:30")
    LIVE_QUEUE_END_TIME: str = Field(default="15:00")
    SLOT_START_TIME: str = Field(default="15:00")
    SLOT_END_TIME: str = Field(default="16:00")
    DAY_CLOSING_TIME: str = Field(default="16:00")
    BOOKING_HORIZON_DAYS: int = Field(default=7)
    MAX_ACTIVE_PER_USER_PER_DOCTOR: int = Field(default=1)
    MAX_DAILY_PER_ACCOUNT: int = Field(default=3)
    NO_SHOW_BLOCK_DAYS: int = Field(default=14)
    NO_SHOW_THRESHOLD: int = Field(default=3)
    WAITLIST_OFFER_MINUTES: int = Field(default=15)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

# Kataloglarni avtomatik yaratish
Path(settings.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
Path(settings.BACKUP_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.LOGS_DIR).mkdir(parents=True, exist_ok=True)


_INSECURE_DEFAULTS = {
    "SUPER_ADMIN_PASSWORD": {"admin12345", "admin", "password"},
    "SECRET_KEY": {"super-secret-clinic-key-change-in-production-32chars"},
}


def validate_production_settings(cfg: Settings = settings) -> None:
    """Production rejimida standart/zaif sirlar bilan ishga tushishni to'xtatadi."""
    if cfg.ENVIRONMENT.lower() != "production":
        return
    problems = [
        name for name, bad in _INSECURE_DEFAULTS.items() if getattr(cfg, name) in bad
    ]
    if len(cfg.SECRET_KEY) < 32 and "SECRET_KEY" not in problems:
        problems.append("SECRET_KEY")
    if cfg.BOT_TOKEN.startswith("123456789:") or "dummy" in cfg.BOT_TOKEN.lower():
        problems.append("BOT_TOKEN")
    if problems:
        raise RuntimeError(
            "Production uchun xavfsiz bo'lmagan sozlamalar: " + ", ".join(problems)
        )


def warn_insecure_settings(cfg: Settings = settings) -> list[str]:
    """Production bo'lmagan muhitda ham zaif/standart sozlamalar haqida ogohlantirish ro'yxati.

    Bu qiymatlarni almashtirish faqat loyiha egasi tomonidan amalga oshiriladi
    (masalan, BOT_TOKEN ni @BotFather orqali yangilash, kuchli parol qo'yish).
    """
    if cfg.ENVIRONMENT.lower() == "production":
        return []

    warnings: list[str] = []
    for name, bad in _INSECURE_DEFAULTS.items():
        if getattr(cfg, name) in bad:
            warnings.append(
                f"{name} standart qiymatda — production'dan oldin almashtiring."
            )
    if cfg.BOT_TOKEN.startswith("123456789:") or "dummy" in cfg.BOT_TOKEN.lower():
        warnings.append(
            "BOT_TOKEN namunali/dummy qiymatda — haqiqiy token kiriting."
        )
    return warnings
