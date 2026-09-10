from app.bot.markdown import markdown_display


def _username(username: str) -> str:
    return markdown_display(username)


def admins_menu_text() -> str:
    return "🔐 *Admins*\n\nChoose an action."


def admins_list_text(admins) -> str:
    return "🔐 *Admins*\n\n" + (
        "\n".join(
            f"• {admin.tg_user_id} @{markdown_display(admin.tg_username)}"
            for admin in admins
        )
        if admins
        else "📭 No admins found."
    )


def user_list_empty_text() -> str:
    return "👤 *Users*\n\n📭 No users found."


def action_prompt(action: str) -> str:
    prompts = {
        "allow": "👤 *Grant access*\n\nSend a username to allow.\nYou can add a full name on the same line.\n\nExamples:\n`@username`\n`@username Full Name`",
        "unallow": "🚫 *Revoke access*\n\nSend a username.\n\nExample: `@username`",
        "ban": "🔴 *Ban user*\n\nSend a username.\n\nExample: `@username`",
        "unban": "✅ *Unban user*\n\nSend a username.\n\nExample: `@username`",
        "delete": "🗑 *Delete user*\n\nSend a username.\n\nExample: `@username`",
    }
    return prompts[action]


def delete_confirm_text(username: str) -> str:
    return (
        f"⚠️ *Delete @{_username(username)}?*\n\n"
        "This removes their bookings, swap offers, and user record.\n\n"
        "This cannot be undone."
    )


def unallow_confirm_text(username: str) -> str:
    return (
        f"⚠️ *Revoke access for @{_username(username)}?*\n\n"
        "They'll be removed from the members chat."
    )


def ban_confirm_text(username: str) -> str:
    return (
        f"🔴 *Ban @{_username(username)}?*\n\n"
        "This revokes access and removes them from the members chat."
    )


def add_admin_prompt_text() -> str:
    return "🔐 *Add admin*\n\nSend a username.\n\nExample: `@username`"


def find_user_prompt_text() -> str:
    return "🔍 *Find user*\n\nSend a username or full name.\n\nExamples:\n`@username`\n`Full Name`\n`Part of Name`"


def find_user_ambiguous_text(users) -> str:
    lines = [
        f"• {markdown_display(user.full_name)} (@{markdown_display(user.tg_username)})"
        for user in users[:10]
    ]
    extra = "" if len(users) <= 10 else f"\n\nAnd {len(users) - 10} more matches."
    return "⚠️ *Multiple matches* — be more specific.\n\n" + "\n".join(lines) + extra


def allow_username_validation_text() -> str:
    return "⚠️ Send a valid username like `@username`.\nYou can optionally add a full name after it."


def access_granted_text(username: str) -> str:
    return f"✅ *Access granted* — @{_username(username)}"


def deleted_user_text(username: str) -> str:
    return f"🗑 *Deleted* — @{_username(username)} and all related data removed."


def revoked_access_text(username: str) -> str:
    return f"🚫 *Access revoked* — @{_username(username)}"


def banned_user_text(username: str, reason: str | None = None) -> str:
    text = f"🔴 *Banned* — @{_username(username)}"
    if reason:
        text += f"\n*Reason:* {markdown_display(reason)}"
    return text


def added_admin_text(username: str) -> str:
    return f"✅ *Admin added* — @{_username(username)}"
