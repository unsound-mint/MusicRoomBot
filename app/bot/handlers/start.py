# app/bot/handlers/start.py
from aiogram import Router, types
from aiogram.filters import Command

from app.bot.keyboards.inline_kb import access_form_kb
from app.bot.start_messages import (
    build_approved_start_text,
    build_new_user_start_text,
    build_pending_access_start_text,
)
from app.bot.ui import get_main_menu_kb
from app.core.database import AsyncSessionLocal
from app.services.admin_service import is_admin
from app.services.booking_status import build_status_summary
from app.services.user_service import resolve_start_user

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message) -> types.Message:
    tg_id = message.from_user.id
    username = (message.from_user.username or "").lower()
    telegram_fullname = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()

    async with AsyncSessionLocal() as db:
        start_user = await resolve_start_user(
            db,
            tg_user_id=tg_id,
            tg_username=username,
            telegram_full_name=telegram_fullname,
        )
        user = start_user.user

        if start_user.created:
            return await message.answer(
                build_new_user_start_text(),
                reply_markup=access_form_kb(),
                parse_mode="Markdown",
            )

        is_admin_user = await is_admin(db, tg_id)
        if not user.allowed and not is_admin_user:
            return await message.answer(
                build_pending_access_start_text(),
                reply_markup=access_form_kb(),
                parse_mode="Markdown",
            )

        summary = await build_status_summary(db, user)
        return await message.answer(
            build_approved_start_text(summary, is_admin_user=is_admin_user),
            reply_markup=await get_main_menu_kb(db, tg_id),
            parse_mode="Markdown",
        )
