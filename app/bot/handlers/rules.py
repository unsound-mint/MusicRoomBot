# app/bot/handlers/rules.py
from aiogram import F, Router, types

from app.bot.markdown import escape_markdown
from app.services.config_runtime import get_runtime_config

router = Router()


@router.message(F.text == "📜 Rules")
async def rules_handler(message: types.Message):
    rules_text = await get_runtime_config("rules_text")
    await message.answer(
        f"📜 *MUSIC ROOM RULES*\n\n{escape_markdown(rules_text)}",
        parse_mode="Markdown",
    )
