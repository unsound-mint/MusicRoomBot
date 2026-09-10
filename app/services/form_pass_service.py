import logging
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

log = logging.getLogger(__name__)

FormPassGrantStatus = Literal["granted", "not_found", "banned", "already_allowed"]


@dataclass(frozen=True)
class FormPassCommand:
    username: str
    score: int
    full_name: str


@dataclass(frozen=True)
class FormPassGrantResult:
    status: FormPassGrantStatus
    user: User | None = None

    @property
    def tg_user_id(self) -> int | None:
        return self.user.tg_user_id if self.user else None

    @property
    def saved_name(self) -> str | None:
        return self.user.full_name if self.user else None


def parse_form_pass_command(text: str | None) -> FormPassCommand | str:
    parts = (text or "").strip().split()
    if len(parts) < 3:
        return "Usage:\n/form_pass @username 90 Full Name"

    username = parts[1].strip().lstrip("@").lower()
    if not username:
        return "Malformed command: missing username."

    score_text = parts[2].strip()
    if score_text.endswith("%"):
        score_text = score_text[:-1].strip()

    try:
        score = int(score_text)
    except ValueError:
        return "Malformed command: score must be a number (e.g. 90)."

    return FormPassCommand(
        username=username,
        score=score,
        full_name=" ".join(parts[3:]).strip(),
    )


async def grant_form_pass_access(
    db: AsyncSession,
    *,
    username: str,
    full_name: str,
) -> FormPassGrantResult:
    username = username.strip().lstrip("@").lower()
    users = (
        (
            await db.execute(
                select(User)
                .where(func.lower(User.tg_username) == username)
                .order_by(User.id.desc())
            )
        )
        .scalars()
        .all()
    )

    user = next((u for u in users if u.tg_user_id is not None), None)
    placeholder_users = [u for u in users if u.tg_user_id is None]

    if user is None and placeholder_users and full_name:
        candidates = (
            (
                await db.execute(
                    select(User)
                    .where(User.tg_user_id.isnot(None))
                    .where(User.full_name == full_name)
                    .order_by(User.id.desc())
                )
            )
            .scalars()
            .all()
        )

        if len(candidates) == 1:
            user = candidates[0]
            for placeholder in placeholder_users:
                await db.delete(placeholder)
            placeholder_users = []
            if username and user.tg_username != username:
                user.tg_username = username

    if not user:
        return FormPassGrantResult(status="not_found")

    if user.banned:
        return FormPassGrantResult(status="banned", user=user)

    if user.allowed:
        return FormPassGrantResult(status="already_allowed", user=user)

    user.allowed = True
    if full_name:
        user.full_name = full_name

    db.add(user)

    if user.tg_user_id is not None:
        for placeholder in placeholder_users:
            await db.delete(placeholder)

    await db.commit()
    await db.refresh(user)
    log.info(
        "Form-pass access flag granted",
        extra={
            "user_id": user.id,
            "tg_user_id": user.tg_user_id,
            "username": username,
        },
    )

    return FormPassGrantResult(status="granted", user=user)
