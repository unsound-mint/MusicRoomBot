import logging

from aiogram import Router, types
from aiogram.filters import Command
from sqlalchemy import select

from app.bot.constants.dates import WEEKDAYS
from app.bot.handlers.admin_shared import check_admin_and_reply
from app.core.database import AsyncSessionLocal
from app.models.booking import Booking
from app.services.booking_service import cancel_booking_by_admin, weekly_reset
from app.services.club_service import set_admin_weekly_slot
from app.services.config_runtime import get_runtime_config
from app.services.config_service import set_config_value
from app.services.config_utils import parse_float, parse_int
from app.services.date_service import get_current_week_date

router = Router()
log = logging.getLogger(__name__)


@router.message(Command("add_weekly"))
async def cmd_add_weekly(message: types.Message):
    if not await check_admin_and_reply(message):
        return

    parts = (message.text or "").split(maxsplit=3)
    if len(parts) < 4:
        await message.answer("Usage: /add_weekly <weekday> <hour> <group>")
        return

    weekday_name = parts[1]
    try:
        hour = int(parts[2])
    except ValueError:
        await message.answer("Hour must be an integer.")
        return

    group = parts[3]
    try:
        weekday_idx = WEEKDAYS.index(weekday_name)
    except ValueError:
        await message.answer("Invalid weekday name. Use one of: " + ", ".join(WEEKDAYS))
        return

    cancelled_count = 0
    async with AsyncSessionLocal() as db:
        await set_admin_weekly_slot(
            db,
            weekday=weekday_idx,
            hour=hour,
            group_name=group,
        )

        target_date = get_current_week_date(weekday_idx)
        booking = (
            await db.execute(
                select(Booking).where(Booking.date == target_date, Booking.hour == hour)
            )
        ).scalar_one_or_none()
        if booking and await cancel_booking_by_admin(
            db,
            booking.id,
            message.bot,
            notify_reason="cancelled by admin because the slot became weekly reserved.",
        ):
            cancelled_count += 1

    result = f"Weekly slot set: {weekday_name} {hour}:00 for {group}."
    if cancelled_count > 0:
        result += f"\n⚠️ {cancelled_count} conflicting booking(s) found and cancelled."
    await message.answer(result)


@router.message(Command("reset_weekly_now"))
async def cmd_reset_weekly_now(message: types.Message):
    if not await check_admin_and_reply(message):
        return

    async with AsyncSessionLocal() as db:
        await weekly_reset(db)

    member_chat_id = await get_runtime_config("member_chat_id")
    member_topic_id = await get_runtime_config("member_topic_id")
    text = "Weekly reset completed. Old non-weekly bookings were cleared."

    if member_chat_id:
        try:
            if member_topic_id:
                await message.bot.send_message(
                    int(member_chat_id),
                    text,
                    message_thread_id=int(member_topic_id),
                )
            else:
                await message.bot.send_message(int(member_chat_id), text)
            await message.answer(
                "Weekly reset completed. Sent notification to members chat."
            )
            return
        except Exception:
            log.exception("Failed to notify members chat after weekly reset")

    await message.answer(
        "Weekly reset completed, but I could not notify the members chat.\n"
        "Check config: member_chat_id (and optional member_topic_id)."
    )


async def _set_int_config(
    message: types.Message,
    *,
    key: str,
    usage: str,
    minimum: int,
    maximum: int,
    suffix: str,
) -> None:
    if not await check_admin_and_reply(message):
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(usage)
        return

    value, error = parse_int(parts[1], minimum=minimum, maximum=maximum)
    if error:
        await message.answer(f"Invalid value: {error}")
        return

    async with AsyncSessionLocal() as db:
        await set_config_value(db, key, str(value))

    await message.answer(f"{key} set to {value}{suffix}")


async def _set_float_config(
    message: types.Message,
    *,
    key: str,
    usage: str,
    minimum: float,
    maximum: float,
    suffix: str,
) -> None:
    if not await check_admin_and_reply(message):
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(usage)
        return

    value, error = parse_float(parts[1], minimum=minimum, maximum=maximum)
    if error:
        await message.answer(f"Invalid value: {error}")
        return

    async with AsyncSessionLocal() as db:
        await set_config_value(db, key, str(value))

    await message.answer(f"{key} set to {value}{suffix}")


@router.message(Command("set_geo_radius"))
async def cmd_set_geo_radius(message: types.Message):
    await _set_float_config(
        message,
        key="geo_radius",
        usage="Usage: /set_geo_radius <meters>",
        minimum=10,
        maximum=10000,
        suffix=" meters",
    )


@router.message(Command("set_late_minutes"))
async def cmd_set_late_minutes(message: types.Message):
    await _set_int_config(
        message,
        key="late_minutes",
        usage="Usage: /set_late_minutes <minutes>",
        minimum=0,
        maximum=1440,
        suffix=" min",
    )


@router.message(Command("set_reminder_hours"))
async def cmd_set_reminder_hours(message: types.Message):
    await _set_int_config(
        message,
        key="reminder_hours",
        usage="Usage: /set_reminder_hours <hours>",
        minimum=0,
        maximum=168,
        suffix=" hours",
    )


@router.message(Command("set_weekly_limit"))
async def cmd_set_weekly_limit(message: types.Message):
    await _set_int_config(
        message,
        key="weekly_limit",
        usage="Usage: /set_weekly_limit <n>",
        minimum=0,
        maximum=100,
        suffix="",
    )


@router.message(Command("set_slot_length"))
async def cmd_set_slot_length(message: types.Message):
    await _set_int_config(
        message,
        key="slot_length",
        usage="Usage: /set_slot_length <minutes>",
        minimum=10,
        maximum=480,
        suffix=" minutes",
    )


async def _set_chat_id_config(message: types.Message, *, key: str, usage: str) -> None:
    if not await check_admin_and_reply(message):
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(usage)
        return

    try:
        value = int(parts[1])
    except ValueError:
        await message.answer(f"{key} must be numeric.")
        return

    async with AsyncSessionLocal() as db:
        await set_config_value(db, key, str(value))

    await message.answer(f"{key} set to {value}")


@router.message(Command("set_geocenter"))
async def cmd_set_geocenter(message: types.Message):
    if not await check_admin_and_reply(message):
        return

    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer("Usage: /set_geocenter <lat> <lon>")
        return

    lat, lat_error = parse_float(parts[1], minimum=-90, maximum=90)
    if lat_error:
        await message.answer("Invalid lat: " + lat_error)
        return
    lon, lon_error = parse_float(parts[2], minimum=-180, maximum=180)
    if lon_error:
        await message.answer("Invalid lon: " + lon_error)
        return

    async with AsyncSessionLocal() as db:
        await set_config_value(db, "geo_center_lat", str(lat))
        await set_config_value(db, "geo_center_lon", str(lon))

    await message.answer(f"Geo center set to {lat}, {lon}")


@router.message(Command("set_admin_chat_id"))
async def cmd_set_admin_chat_id(message: types.Message):
    await _set_chat_id_config(
        message,
        key="admin_chat_id",
        usage="Usage: /set_admin_chat_id <chat_id>",
    )


@router.message(Command("set_warning_chat_id"))
async def cmd_set_warning_chat_id(message: types.Message):
    await _set_chat_id_config(
        message,
        key="warning_chat_id",
        usage="Usage: /set_warning_chat_id <chat_id>",
    )


@router.message(Command("set_member_chat_id"))
async def cmd_set_member_chat_id(message: types.Message):
    await _set_chat_id_config(
        message,
        key="member_chat_id",
        usage="Usage: /set_member_chat_id <chat_id>",
    )


@router.message(Command("set_member_topic_id"))
async def cmd_set_member_topic_id(message: types.Message):
    await _set_chat_id_config(
        message,
        key="member_topic_id",
        usage="Usage: /set_member_topic_id <topic_id>",
    )


@router.message(Command("set_access_chat_id"))
async def cmd_set_access_chat_id(message: types.Message):
    await _set_chat_id_config(
        message,
        key="access_chat_id",
        usage="Usage: /set_access_chat_id <chat_id>",
    )


@router.message(Command("update_rules"))
async def cmd_update_rules(message: types.Message):
    if not await check_admin_and_reply(message):
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Usage:\n/update_rules <new rules text>\n\nExample:\n/update_rules New rules here..."
        )
        return

    async with AsyncSessionLocal() as db:
        await set_config_value(db, "rules_text", parts[1].strip())
    await message.answer("Rules updated successfully.\n")


@router.message(Command("working_hours"))
async def cmd_working_hours(message: types.Message):
    if not await check_admin_and_reply(message):
        return

    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer(
            "Usage:\n/working_hours <weekday> <start-end>\nExample:\n/working_hours Saturday 9-23"
        )
        return

    weekday = parts[1].capitalize()
    hours = parts[2]
    if weekday not in WEEKDAYS:
        await message.answer("Invalid weekday. Use Monday-Sunday.")
        return
    if "-" not in hours:
        await message.answer("Invalid format. Use <start>-<end> (e.g., 9-23)")
        return

    try:
        start_str, end_str = hours.split("-", 1)
        start = int(start_str)
        end = int(end_str)
    except ValueError:
        await message.answer("Start and end must be integers. Example: 9-23")
        return

    if not (0 <= start <= 23 and 1 <= end <= 24 and start < end):
        await message.answer("Invalid time range. Example: 9-23")
        return

    async with AsyncSessionLocal() as db:
        await set_config_value(db, f"working_hours_{weekday}", f"{start}-{end}")

    await message.answer(f"Working hours for {weekday} updated to {start}:00 - {end}:00")
