# app/bot/handlers/warning_appeal.py
import logging

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select

from app.bot.keyboards.admin_inline_kb import warning_appeal_review_kb
from app.bot.keyboards.inline_kb import warning_appeal_cancel_kb
from app.bot.ui import safe_answer_callback
from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.services.admin_service import is_admin
from app.services.config_runtime import get_runtime_config
from app.services.warning_service import (
    MAX_WARNINGS,
    approve_warning_appeal,
    revert_latest_warning,
)

log = logging.getLogger(__name__)

router = Router()


class WarningAppealStates(StatesGroup):
    waiting_photo = State()


@router.callback_query(F.data.startswith("warn_appeal_start_"))
async def warn_appeal_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    raw = callback.data.removeprefix("warn_appeal_start_")
    try:
        user_db_id = int(raw)
    except ValueError:
        await callback.answer("Invalid appeal link.", show_alert=True)
        return

    await safe_answer_callback(callback)
    await state.set_state(WarningAppealStates.waiting_photo)
    await state.update_data(appeal_user_db_id=user_db_id)

    assert callback.message is not None
    await callback.message.answer(
        "Send evidence for your appeal.\n"
        "For attendance warnings, send a photo from the attendance journal.",
        reply_markup=warning_appeal_cancel_kb(),
    )


@router.callback_query(F.data == "warn_appeal_cancel")
async def warn_appeal_cancel(callback: types.CallbackQuery, state: FSMContext) -> None:
    await safe_answer_callback(callback)
    await state.clear()
    assert callback.message is not None
    await callback.message.edit_text("❌ Appeal cancelled.")


@router.message(WarningAppealStates.waiting_photo, F.photo)
async def warn_appeal_photo_received(
    message: types.Message, state: FSMContext
) -> None:
    data = await state.get_data()
    user_db_id: int | None = data.get("appeal_user_db_id")
    if user_db_id is None:
        await state.clear()
        return

    await state.clear()

    admin_chat_id = await get_runtime_config("admin_chat_id")
    if not admin_chat_id:
        await message.answer(
            "The appeal system is not configured yet. Please contact an admin directly."
        )
        return

    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.id == user_db_id))
        ).scalar_one_or_none()

    if not user:
        await message.answer("Could not find your account. Please contact an admin.")
        return

    display = user.full_name or (
        f"@{user.tg_username}" if user.tg_username else f"id={user_db_id}"
    )
    status = "BANNED" if user.banned else f"{user.warnings or 0}/{MAX_WARNINGS} warnings"
    caption = (
        f"⚠️ Warning Appeal\n"
        f"User: {display}\n"
        f"Status: {status}"
    )

    photo = message.photo[-1]  # largest size
    assert message.bot is not None
    try:
        await message.bot.send_photo(
            chat_id=admin_chat_id,
            photo=photo.file_id,
            caption=caption,
            reply_markup=warning_appeal_review_kb(user_db_id),
        )
    except Exception:
        log.exception(
            "Failed to forward appeal photo to admin chat",
            extra={"user_db_id": user_db_id},
        )
        await message.answer(
            "Failed to send your appeal. Please contact an admin directly."
        )
        return

    await message.answer(
        "✅ *Appeal submitted.*\n\nAn admin will review it shortly.",
        parse_mode="Markdown",
    )


@router.message(WarningAppealStates.waiting_photo, ~F.photo)
async def warn_appeal_wrong_content(message: types.Message) -> None:
    await message.answer(
        "Please send a photo as evidence, or tap Cancel to abort.",
        reply_markup=warning_appeal_cancel_kb(),
    )


@router.callback_query(F.data.startswith("warn_appeal_approve_"))
async def warn_appeal_approve(callback: types.CallbackQuery) -> None:
    async with AsyncSessionLocal() as db:
        if not await is_admin(db, callback.from_user.id):
            await callback.answer("Admin only.", show_alert=True)
            return

    raw = callback.data.removeprefix("warn_appeal_approve_")
    try:
        user_db_id = int(raw)
    except ValueError:
        await callback.answer("Invalid appeal data.", show_alert=True)
        return

    await safe_answer_callback(callback)

    async with AsyncSessionLocal() as db:
        found = await approve_warning_appeal(db=db, bot=callback.bot, user_db_id=user_db_id)

    assert callback.message is not None
    reviewer = callback.from_user.full_name or callback.from_user.username or "admin"

    if not found:
        try:
            await callback.message.edit_caption(
                caption=(callback.message.caption or "") + "\n\n❌ User not found."
            )
        except Exception:
            log.exception(
                "Failed to edit appeal message after missing user",
                extra={"user_db_id": user_db_id},
            )
        return

    try:
        await callback.message.edit_caption(
            caption=(callback.message.caption or "") + f"\n\n✅ Approved by {reviewer}",
            reply_markup=None,
        )
    except Exception:
        log.exception("Failed to edit appeal message after approval")


@router.callback_query(F.data.startswith("warn_revert_"))
async def warn_revert(callback: types.CallbackQuery) -> None:
    async with AsyncSessionLocal() as db:
        if not await is_admin(db, callback.from_user.id):
            await callback.answer("Admin only.", show_alert=True)
            return

    raw = callback.data.removeprefix("warn_revert_")
    try:
        user_db_id = int(raw)
    except ValueError:
        await callback.answer("Invalid warning data.", show_alert=True)
        return

    await safe_answer_callback(callback)

    async with AsyncSessionLocal() as db:
        result = await revert_latest_warning(
            db=db,
            bot=callback.bot,
            user_db_id=user_db_id,
            decrement_ban_count=True,
        )

    assert callback.message is not None
    reviewer = callback.from_user.full_name or callback.from_user.username or "admin"

    if result is None:
        try:
            await callback.message.edit_text(
                (callback.message.text or "") + "\n\n❌ User not found.",
                reply_markup=None,
            )
        except Exception:
            log.exception(
                "Failed to edit warning message after missing user",
                extra={"user_db_id": user_db_id},
            )
        return

    action = "Warning and ban reverted" if result.was_banned else "Warning reverted"
    try:
        await callback.message.edit_text(
            (callback.message.text or "")
            + f"\n\n✅ {action} by {reviewer}."
            + f"\nWarnings: {result.warnings}/{MAX_WARNINGS}"
            + f"\nBan count: {result.ban_count}",
            reply_markup=None,
        )
    except Exception:
        log.exception("Failed to edit warning message after revert")


@router.callback_query(F.data.startswith("warn_appeal_decline_"))
async def warn_appeal_decline(callback: types.CallbackQuery) -> None:
    async with AsyncSessionLocal() as db:
        if not await is_admin(db, callback.from_user.id):
            await callback.answer("Admin only.", show_alert=True)
            return

    raw = callback.data.removeprefix("warn_appeal_decline_")
    try:
        user_db_id = int(raw)
    except ValueError:
        await callback.answer("Invalid appeal data.", show_alert=True)
        return

    await safe_answer_callback(callback)

    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.id == user_db_id))
        ).scalar_one_or_none()

    reviewer = callback.from_user.full_name or callback.from_user.username or "admin"

    if user and user.tg_user_id:
        try:
            assert callback.bot is not None
            await callback.bot.send_message(
                user.tg_user_id,
                "❌ Your warning appeal was declined.\n\nContact an admin if you have questions.",
            )
        except Exception:
            log.exception(
                "Failed to notify user of appeal decline",
                extra={"user_db_id": user_db_id},
            )

    assert callback.message is not None
    try:
        await callback.message.edit_caption(
            caption=(callback.message.caption or "") + f"\n\n❌ Declined by {reviewer}",
            reply_markup=None,
        )
    except Exception:
        log.exception("Failed to edit appeal message after decline")
