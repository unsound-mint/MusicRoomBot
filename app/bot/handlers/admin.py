# app/bot/handlers/admin.py
from aiogram import Router

from app.bot.handlers.admin_bookings import router as admin_bookings_router
from app.bot.handlers.admin_bulk import router as admin_bulk_router
from app.bot.handlers.admin_clubs import router as admin_clubs_router
from app.bot.handlers.admin_config import router as admin_config_router
from app.bot.handlers.admin_dashboard import router as admin_dashboard_router
from app.bot.handlers.admin_equipment_requests import (
    router as admin_equipment_requests_router,
)
from app.bot.handlers.admin_inputs import router as admin_inputs_router
from app.bot.handlers.admin_legacy import router as admin_legacy_router
from app.bot.handlers.admin_system import router as admin_system_router
from app.bot.handlers.admin_users import router as admin_users_router
from app.bot.handlers.admin_warnings import router as admin_warnings_router

router = Router()
router.include_router(admin_dashboard_router)
router.include_router(admin_bookings_router)
router.include_router(admin_bulk_router)
router.include_router(admin_clubs_router)
router.include_router(admin_config_router)
router.include_router(admin_equipment_requests_router)
router.include_router(admin_inputs_router)
router.include_router(admin_system_router)
router.include_router(admin_users_router)
router.include_router(admin_warnings_router)
router.include_router(admin_legacy_router)
