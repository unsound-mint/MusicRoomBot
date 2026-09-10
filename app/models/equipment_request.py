from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class EquipmentRequest(Base):
    __tablename__ = "equipment_requests"
    __table_args__ = (
        Index("ix_equipment_requests_status", "status"),
        Index("ix_equipment_requests_requester_tg_user_id", "requester_tg_user_id"),
        Index(
            "ix_equipment_requests_review_chat_message",
            "review_chat_id",
            "review_message_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    requester_tg_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    requester_username: Mapped[str | None] = mapped_column(String, nullable=True)

    full_name: Mapped[str] = mapped_column(String, nullable=False)
    club_name: Mapped[str] = mapped_column(String, nullable=False)
    event_name: Mapped[str] = mapped_column(String, nullable=False)
    venue: Mapped[str] = mapped_column(String, nullable=False)
    equipment_text: Mapped[str] = mapped_column(Text, nullable=False)
    needed_at_text: Mapped[str] = mapped_column(Text, nullable=False)
    reason_text: Mapped[str] = mapped_column(Text, nullable=False)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="submitted",
        server_default=text("'submitted'"),
    )
    admin_tg_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    review_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    review_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    equipment_post_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    equipment_post_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    requester_dm_sent: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("FALSE"),
    )
    equipment_post_sent: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("FALSE"),
    )
    requester_dm_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    equipment_post_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    ranges = relationship(
        "EquipmentRequestRange",
        back_populates="equipment_request",
        cascade="all, delete-orphan",
        order_by="EquipmentRequestRange.sort_order",
    )
