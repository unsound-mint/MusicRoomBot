# app/models/swap_offer.py
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SwapOffer(Base):
    __tablename__ = "swap_offers"

    __table_args__ = (
        # Fast lookups by participants
        Index("ix_swap_offers_giver_user_id", "giver_user_id"),
        Index("ix_swap_offers_receiver_user_id", "receiver_user_id"),
        # Useful for cleanup / reporting (optional but cheap)
        Index("ix_swap_offers_give_slot", "give_date", "give_hour"),
        Index("ix_swap_offers_want_slot", "want_date", "want_hour"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    giver_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    receiver_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    give_date: Mapped[date] = mapped_column(Date, nullable=False)
    give_hour: Mapped[int] = mapped_column(Integer, nullable=False)

    want_date: Mapped[date] = mapped_column(Date, nullable=False)
    want_hour: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
