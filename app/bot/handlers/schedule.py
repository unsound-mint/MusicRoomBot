# app/bot/handlers/schedule.py
from aiogram import F, Router, types

from app.core.database import AsyncSessionLocal
from app.services.schedule_service import build_schedule_text

router = Router()


@router.message(F.text == "📅 Schedule")
async def schedule_handler(message: types.Message) -> None:
    async with AsyncSessionLocal() as db:
        text = await build_schedule_text(db)

    await message.answer(text, parse_mode="Markdown")
