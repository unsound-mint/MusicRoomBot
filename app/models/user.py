# app/models/user.py
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Nullable because you allow placeholder users until they send /start
    tg_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        unique=True,
        nullable=True,
        index=True,
    )
    tg_username: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        index=True,
    )

    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    warnings: Mapped[int] = mapped_column(Integer, default=0)

    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    ban_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    ban_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    banned_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
