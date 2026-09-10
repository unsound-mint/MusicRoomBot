# app/bot/main.py
import asyncio

from aiogram import Bot, Dispatcher

from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.booking import router as booking_router
from app.bot.handlers.club_slots import router as club_slots_router
from app.bot.handlers.equipment_request import router as equipment_request_router
from app.bot.handlers.flash_book import router as flash_book_router
from app.bot.handlers.form_passed import router as form_passed_router
from app.bot.handlers.location import router as location_router
from app.bot.handlers.my_bookings import router as my_bookings_router
from app.bot.handlers.rules import router as rules_router
from app.bot.handlers.schedule import router as schedule_router
from app.bot.handlers.start import router as start_router
from app.bot.handlers.swap import router as swap_router
from app.bot.handlers.warning_appeal import router as warning_appeal_router
from app.core.config import LOG_LEVEL, require_bot_token
from app.core.database import dispose_engine
from app.core.logging import configure_logging
from app.services.scheduler_service import setup_scheduler, shutdown_scheduler

configure_logging(LOG_LEVEL)


async def on_startup(bot: Bot, **_: object) -> None:
    setup_scheduler(bot)


async def on_shutdown(**_: object) -> None:
    shutdown_scheduler(wait=False)
    await dispose_engine()


async def main():
    bot = Bot(require_bot_token())
    dp = Dispatcher()

    dp.include_router(start_router)
    dp.include_router(booking_router)
    dp.include_router(club_slots_router)
    dp.include_router(equipment_request_router)
    dp.include_router(flash_book_router)
    dp.include_router(schedule_router)
    dp.include_router(my_bookings_router)
    dp.include_router(location_router)
    dp.include_router(rules_router)
    dp.include_router(swap_router)
    dp.include_router(admin_router)
    dp.include_router(form_passed_router)
    dp.include_router(warning_appeal_router)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
