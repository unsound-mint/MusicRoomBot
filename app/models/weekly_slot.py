# app/models/weekly_slot.py
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.club import Club


class WeeklySlot(Base):
    __tablename__ = "weekly_slots"

    __table_args__ = (
        UniqueConstraint("weekday", "hour", name="uq_weekly_weekday_hour"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    hour: Mapped[int] = mapped_column(Integer, nullable=False)
    group_name: Mapped[str] = mapped_column(String, nullable=False)
    club_id: Mapped[int | None] = mapped_column(
        ForeignKey("clubs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    club: Mapped["Club | None"] = relationship("Club", back_populates="weekly_slots")
