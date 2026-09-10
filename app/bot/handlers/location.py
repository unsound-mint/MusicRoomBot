# app/bot/handlers/location.py
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router, types
from sqlalchemy import select

from app.bot.constants.dates import WEEKDAYS
from app.bot.markdown import MARKDOWN_PARSE_MODE
from app.bot.ui import get_main_menu_kb
from app.core.config import TIMEZONE
from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.services.admin_service import is_admin
from app.services.attendance_service import get_current_booking, record_absence
from app.services.config_runtime import get_runtime_config
from app.services.geo_service import get_geo_config, mark_attendance_chain_verified
from app.services.warning_service import add_warning
from app.utils.geo import distance_meters

router = Router()


@router.message(F.location)
async def handle_location(message: types.Message) -> None:
    lat = message.location.latitude
    lon = message.location.longitude
    tg_id = message.from_user.id

    now = datetime.now(tz=ZoneInfo(TIMEZONE))

    geo_config = await get_geo_config()
    distance = distance_meters(lat, lon, geo_config.center_lat, geo_config.center_lon)

    async with AsyncSessionLocal() as db:
        admin_flag = await is_admin(db, tg_id)

        # ADMIN MODE: distance check only
        if admin_flag:
            status = "inside" if distance <= geo_config.radius else "outside"
            return await message.answer(
                "🛰 *Admin distance check*\n\n"
                f"📏 {int(distance)} m — {'✅ inside' if status == 'inside' else '⚠️ outside'} geofence",
                parse_mode=MARKDOWN_PARSE_MODE,
            )

        user = (
            await db.execute(select(User).where(User.tg_user_id == tg_id))
        ).scalar_one_or_none()
        if not user:
            return await message.answer("⚠️ You're not registered.")

        booking = await get_current_booking(db, user.id)
        if not booking:
            return await message.answer("📭 No booking right now.")

        # ----------------------------------------------------
        # DUPLICATE / LATE CHECK
        # ----------------------------------------------------
        if booking.absence_reported:
            if booking.attendance_verified:
                return await message.answer(
                    "✅ *Already checked in*\n\nHave a great session!",
                    reply_markup=await get_main_menu_kb(db, tg_id),
                    parse_mode=MARKDOWN_PARSE_MODE,
                )
            else:
                return await message.answer(
                    "⏰ *Check-in closed*\n\n"
                    "*Status:* Marked absent\n\n"
                    "Contact an admin if this is a mistake.",
                    reply_markup=await get_main_menu_kb(db, tg_id),
                    parse_mode=MARKDOWN_PARSE_MODE,
                )

        # ----------------------------------------------------
        # ⏱ DEADLINE CHECK
        # ----------------------------------------------------
        late_minutes = await get_runtime_config("late_minutes")
        try:
            late_minutes = int(late_minutes)
        except Exception:
            late_minutes = 10

        booking_start = datetime.combine(
            booking.date,
            time(booking.hour, 0),
        ).replace(tzinfo=ZoneInfo(TIMEZONE))

        deadline = booking_start + timedelta(minutes=late_minutes)

        if now >= deadline:
            await record_absence(db, booking.id, user.id)
            await add_warning(
                db=db,
                bot=getattr(message, "bot", None),
                user_id=user.id,
                reason=f"Absent for {WEEKDAYS[booking.date.weekday()]} at {booking.hour:02d}:00",
            )
            return await message.answer(
                "⏰ *Check-in closed*\n\n"
                "*Status:* Marked absent\n\n"
                "Contact an admin if this is a mistake.",
                reply_markup=await get_main_menu_kb(db, tg_id),
                parse_mode=MARKDOWN_PARSE_MODE,
            )

        # ----------------------------------------------------
        # GEO CHECK
        # ----------------------------------------------------
        if distance > geo_config.radius:
            await message.answer(
                "📍 *Too far from the Music Room*\n\n"
                f"📏 *Distance:* {int(distance)} m\n\n"
                "Move closer and send your location again.",
                parse_mode="Markdown",
            )
            return await message.answer(
                "\u200b",
                reply_markup=await get_main_menu_kb(db, tg_id),
            )

        # ----------------------------------------------------
        # SUCCESS — CONFIRM ATTENDANCE
        # ----------------------------------------------------
        await mark_attendance_chain_verified(db, user, booking, lat, lon, distance)

    await message.answer(
        f"✅ *Check-in confirmed*\n\n📏 *Distance:* {int(distance)} m\n\nHave a great session!",
        reply_markup=await get_main_menu_kb(db, tg_id),
        parse_mode=MARKDOWN_PARSE_MODE,
    )


@router.callback_query(F.data == "loc_send")
async def prompt_inline_location(callback: types.CallbackQuery) -> None:
    await callback.answer()
    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.tg_user_id == callback.from_user.id))
        ).scalar_one_or_none()
        if user:
            booking = await get_current_booking(db, user.id)
            if not booking:
                return await callback.message.answer("📭 No booking right now.")

    await callback.message.edit_text(
        "📍 *Send your location*\n\n"
        "Tap the Send Location button at the top of the keyboard.",
        parse_mode=MARKDOWN_PARSE_MODE,
    )
    async with AsyncSessionLocal() as db:
        reply_markup = await get_main_menu_kb(db, callback.from_user.id)
    await callback.message.answer(
        "\u200b",
        reply_markup=reply_markup,
    )


@router.message(F.location.is_(None) & F.text.is_("📍 Send Location"))
async def location_permission_error(message: types.Message) -> None:
    tg_id = message.from_user.id
    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.tg_user_id == tg_id))
        ).scalar_one_or_none()
        if user:
            booking = await get_current_booking(db, user.id)
            if not booking:
                return await message.answer(
                    "📭 No active booking.\n\n"
                    "You can only use this button during your reserved session.",
                    reply_markup=await get_main_menu_kb(db, tg_id),
                )

        await message.answer(
            "📍 *Location access is blocked*\n\n"
            "Go to Settings → Apps → Telegram → Permissions → enable Location, "
            "then send your location again.",
            parse_mode="Markdown",
            reply_markup=await get_main_menu_kb(db, tg_id),
        )
