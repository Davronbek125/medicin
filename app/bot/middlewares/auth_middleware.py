"""
Telegram Bot - Foydalanuvchi va tilni yuklash middleware moduli.
"""
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser
from app.db.connection import get_db
from app.db.repositories import users_repo, staff_repo


class UserAuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        event_from_user: TgUser = data.get("event_from_user")
        if not event_from_user:
            return await handler(event, data)

        telegram_id = event_from_user.id
        
        async with get_db() as db:
            user = await users_repo.get_user_by_telegram_id(db, telegram_id)
            staff = await staff_repo.get_staff_by_telegram_id(db, telegram_id)

        data["user"] = user
        data["lang"] = user["til"] if user else "uz"
        data["staff"] = staff
        data["is_staff"] = bool(staff)

        return await handler(event, data)
