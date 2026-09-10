from app.bot.keyboards.inline_kb import access_form_kb
from app.bot.markdown import MARKDOWN_PARSE_MODE
from app.bot.ui import edit_or_answer
from app.services.user_service import get_user_by_tg_id

REGISTER_FIRST_TEXT = "Send /start to register first."
ACCESS_PENDING_TEXT = (
    "🟡 *Access: Pending*\n\n"
    "Fill out the form if you haven't already.\n"
    "You'll be notified here once approved."
)
ACCESS_PENDING_EDIT_TEXT = (
    "🟡 *Access: Pending*\n\n"
    "Fill out the form if you haven't already.\n"
    "You'll be notified here once approved."
)


async def _respond(target, text: str, *, use_edit: bool, **kwargs):
    if "*" in text and "parse_mode" not in kwargs:
        kwargs["parse_mode"] = MARKDOWN_PARSE_MODE
    if use_edit:
        return await edit_or_answer(target, text, **kwargs)
    return await target.answer(text, **kwargs)


async def require_registered_user(target, db, tg_user_id: int, *, use_edit: bool):
    user = await get_user_by_tg_id(db, tg_user_id)
    if not user:
        await _respond(target, REGISTER_FIRST_TEXT, use_edit=use_edit)
        return None
    return user


async def require_allowed_user(
    target,
    db,
    tg_user_id: int,
    *,
    use_edit: bool,
    pending_text: str,
):
    user = await require_registered_user(target, db, tg_user_id, use_edit=use_edit)
    if not user:
        return None
    if not user.allowed:
        await _respond(
            target,
            pending_text,
            use_edit=use_edit,
            reply_markup=access_form_kb(),
        )
        return None
    return user
