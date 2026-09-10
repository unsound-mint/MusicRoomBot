# app/bot/handlers/admin_dashboard.py
from aiogram import F, Router, types

from app.bot.handlers.admin_shared import (
    check_admin_and_reply,
    check_admin_callback,
    render_admin_home,
    render_bookings_menu,
    render_bulk_menu,
    render_clubs_menu,
    render_config_menu,
    render_system_menu,
    render_users_menu,
)
from app.bot.ui import safe_answer_callback

router = Router()


@router.message(F.text == "🛠 Admin")
async def handle_admin_commands_button(message: types.Message):
    if not await check_admin_and_reply(message):
        return
    await render_admin_home(message)


@router.callback_query(F.data == "admin_home")
async def admin_home_callback(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    await render_admin_home(callback)


@router.callback_query(F.data == "admin_users")
async def admin_users_callback(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    await render_users_menu(callback)


@router.callback_query(F.data == "admin_bookings")
async def admin_bookings_callback(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    await render_bookings_menu(callback)


@router.callback_query(F.data == "admin_clubs")
async def admin_clubs_callback(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    await render_clubs_menu(callback)


@router.callback_query(F.data == "admin_cfg")
async def admin_cfg_callback(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    await render_config_menu(callback)


@router.callback_query(F.data == "admin_sys")
async def admin_sys_callback(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    await render_system_menu(callback)


@router.callback_query(F.data == "admin_bulk")
async def admin_bulk_callback(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    await render_bulk_menu(callback)
