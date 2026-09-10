# app/bot/handlers/admin_config.py
from aiogram import Router, types
from aiogram.fsm.context import FSMContext

from app.bot.handlers.admin_config_flow import handle_admin_config_callback
from app.bot.handlers.admin_shared import check_admin_callback
from app.bot.ui import safe_answer_callback

router = Router()


def is_admin_config_callback(callback: types.CallbackQuery) -> bool:
    data = callback.data or ""
    return data.startswith("admin_cfg_") and data != "admin_cfg_hours_confirm_state"


@router.callback_query(is_admin_config_callback)
async def admin_config_callbacks(callback: types.CallbackQuery, state: FSMContext):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    data = callback.data
    return await handle_admin_config_callback(callback, state, data)
