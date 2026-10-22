"""
Telegram Bot - Anti-flood (throttling) middleware moduli.
"""
import time
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser, CallbackQuery


class AntiFloodMiddleware(BaseMiddleware):
    def __init__(self, limit_seconds: float = 0.5):
        super().__init__()
        self.limit_seconds = limit_seconds
        self.user_timestamps: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        event_from_user: TgUser = data.get("event_from_user")
        if not event_from_user:
            return await handler(event, data)

        now = time.monotonic()
        user_id = event_from_user.id
        last_time = self.user_timestamps.get(user_id, 0)

        if now - last_time < self.limit_seconds:
            # Haddan tashqari tez bosilganda takroriy so'rovni e'tiborsiz qoldirish.
            # Message va CallbackQuery uchun mos parametrlar farq qiladi: Message.answer()
            # `show_alert` ni qabul qilmaydi, CallbackQuery.answer() esa matnni faqat
            # `show_alert=True` bo'lganda ko'rsatadi.
            try:
                if isinstance(event, CallbackQuery):
                    await event.answer("⚠️ Iltimos, biroz kuting...", show_alert=True)
                elif hasattr(event, "answer") and callable(getattr(event, "answer")):
                    await event.answer("⚠️ Iltimos, biroz kuting...")
            except Exception:
                pass
            return None

        self.user_timestamps[user_id] = now
        if len(self.user_timestamps) > 10000:
            threshold = now - 60
            self.user_timestamps = {k: v for k, v in self.user_timestamps.items() if v > threshold}

        return await handler(event, data)
