# app/bot/handlers/admin_bulk.py
import csv
import io
import logging

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from app.bot.constants.links import FORMS_LINK
from app.bot.handlers.admin_shared import (
    BulkStates,
    canon_username,
    check_admin_and_reply,
    check_admin_callback,
)
from app.bot.keyboards.admin_inline_kb import admin_back_kb, admin_next_actions_kb
from app.bot.ui import edit_or_answer, safe_answer_callback
from app.core.database import AsyncSessionLocal
from app.services.admin_service import is_admin
from app.services.admin_user_commands import sync_allowed_members_from_usernames
from app.services.config_runtime import get_runtime_config

router = Router()
log = logging.getLogger(__name__)


def _bulk_next_kb():
    return admin_next_actions_kb(
        [("Upload another CSV", "admin_bulk_upload")],
        back_data="admin_bulk",
        back_text="⬅️ Back to bulk sync",
    )


@router.message(Command("bulk_update_members"))
async def cmd_bulk_update_members(message: types.Message, state: FSMContext):
    if not await check_admin_and_reply(message):
        return
    await state.set_state(BulkStates.waiting_csv)
    await message.answer(
        "Please send the CSV file exported from Google Sheets.\nExpected columns: full_name,username",
        reply_markup=admin_back_kb("admin_bulk"),
    )


@router.callback_query(F.data == "admin_bulk_upload")
async def admin_bulk_upload(callback: types.CallbackQuery, state: FSMContext):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    await state.set_state(BulkStates.waiting_csv)
    await edit_or_answer(
        callback,
        "Bulk sync\n\nSend the CSV file exported from Google Sheets.\nExpected columns: full_name,username",
        reply_markup=admin_back_kb("admin_bulk"),
    )


@router.message(BulkStates.waiting_csv, F.document.mime_type == "text/csv")
async def handle_bulk_csv(message: types.Message, state: FSMContext):
    if not await check_admin_and_reply(message):
        await state.clear()
        return

    try:
        file = await message.bot.get_file(message.document.file_id)
        content = await message.bot.download_file(file.file_path)
        csv_text = content.read().decode("utf-8")
    except Exception:
        await state.clear()
        return await message.answer(
            "Failed to download CSV file.",
            reply_markup=_bulk_next_kb(),
        )

    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    if len(rows) < 2:
        await state.clear()
        return await message.answer(
            "CSV file is empty or invalid.",
            reply_markup=_bulk_next_kb(),
        )

    def _norm_cell(cell: str) -> str:
        return cell.lstrip("\ufeff").strip().lower()

    def _is_blank_row(row: list[str]) -> bool:
        return all(not cell.strip() for cell in row)

    nonblank_rows = [row for row in rows if not _is_blank_row(row)]
    if not nonblank_rows:
        await state.clear()
        return await message.answer(
            "CSV file is empty or invalid.",
            reply_markup=_bulk_next_kb(),
        )

    header_idx = 0
    for idx, row in enumerate(nonblank_rows[:10]):
        normalized = [_norm_cell(cell) for cell in row]
        if any(key in normalized for key in ("username", "tg_username", "telegram")):
            header_idx = idx
            break

    header = nonblank_rows[header_idx]
    data_rows = nonblank_rows[header_idx + 1 :]
    normalized = [_norm_cell(cell) for cell in header]

    username_col = None
    for key in ("username", "tg_username", "telegram"):
        if key in normalized:
            username_col = normalized.index(key)
            break
    if username_col is None:
        await state.clear()
        return await message.answer(
            "Could not detect username column.",
            reply_markup=_bulk_next_kb(),
        )

    allowed_usernames = set()
    for row in data_rows:
        if len(row) <= username_col:
            continue
        username = canon_username(row[username_col].strip())
        if username:
            allowed_usernames.add(username)

    if not allowed_usernames:
        await state.clear()
        return await message.answer(
            "CSV contains no usernames.",
            reply_markup=_bulk_next_kb(),
        )

    async with AsyncSessionLocal() as db:
        sync_result = await sync_allowed_members_from_usernames(db, allowed_usernames)

    kicked = 0
    notified = 0
    notify_failed = 0
    kick_skipped_no_user_id = 0
    kick_skipped_admin = 0
    kick_failed = 0
    member_chat_id = await get_runtime_config("member_chat_id")

    if member_chat_id:
        async with AsyncSessionLocal() as db:
            for user in sync_result.revoked_users:
                if not user.tg_user_id:
                    kick_skipped_no_user_id += 1
                    continue
                if await is_admin(db, user.tg_user_id):
                    kick_skipped_admin += 1
                    continue
                try:
                    await message.bot.ban_chat_member(
                        chat_id=member_chat_id, user_id=user.tg_user_id
                    )
                    await message.bot.unban_chat_member(
                        chat_id=member_chat_id, user_id=user.tg_user_id
                    )
                    kicked += 1
                    try:
                        await message.bot.send_message(
                            user.tg_user_id,
                            "Your access was removed because your information was not found in the current members sheet.\n\n"
                            "To regain access, please follow the standard procedure and complete the Google Form:\n"
                            f"{FORMS_LINK}",
                        )
                        notified += 1
                    except Exception:
                        notify_failed += 1
                        log.exception("Failed to notify revoked user", extra={"username": user.tg_username})
                except Exception:
                    kick_failed += 1
                    log.exception("Failed to kick revoked user", extra={"username": user.tg_username})

    await state.clear()
    await message.answer(
        "✅ Bulk update complete.\n\n"
        f"Revoked: {sync_result.updated_revoked}"
        + (
            f" (admins skipped: {sync_result.revoked_admins_skipped})"
            if sync_result.revoked_admins_skipped
            else ""
        )
        + "\n"
        f"Kicked from members chat: {kicked}"
        + (
            f" (skipped no tg_user_id: {kick_skipped_no_user_id}, skipped admin: {kick_skipped_admin}, failed: {kick_failed})"
            if (kick_skipped_no_user_id or kick_skipped_admin or kick_failed)
            else ""
        )
        + (
            f"\nNotified kicked users (DM): {notified}" + (f" (failed: {notify_failed})" if notify_failed else "")
            if (notified or notify_failed)
            else ""
        ),
        reply_markup=_bulk_next_kb(),
    )
