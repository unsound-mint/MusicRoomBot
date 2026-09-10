from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.weekly_slot import WeeklySlot


class Club(Base):
    __tablename__ = "clubs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    leaders: Mapped[list["ClubLeader"]] = relationship(
        "ClubLeader",
        back_populates="club",
        cascade="all, delete-orphan",
    )
    weekly_slots: Mapped[list["WeeklySlot"]] = relationship(
        "WeeklySlot",
        back_populates="club",
    )


class ClubLeader(Base):
    __tablename__ = "club_leaders"

    __table_args__ = (
        UniqueConstraint("club_id", "user_id", name="uq_club_leader_club_user"),
        Index("ix_club_leaders_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int | None] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"),
        nullable=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    club: Mapped["Club"] = relationship("Club", back_populates="leaders")
    user: Mapped["User"] = relationship("User")


class ClubSlotCancellation(Base):
    __tablename__ = "club_slot_cancellations"

    __table_args__ = (
        UniqueConstraint(
            "weekly_slot_id",
            "date",
            name="uq_club_slot_cancellation_slot_date",
        ),
        Index("ix_club_slot_cancellations_date", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int | None] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"),
        nullable=True,
    )
    weekly_slot_id: Mapped[int] = mapped_column(
        ForeignKey("weekly_slots.id", ondelete="CASCADE"),
        nullable=False,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    cancelled_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
    cancelled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    club: Mapped["Club | None"] = relationship("Club")
    weekly_slot: Mapped["WeeklySlot"] = relationship("WeeklySlot")
    cancelled_by: Mapped["User"] = relationship("User")
