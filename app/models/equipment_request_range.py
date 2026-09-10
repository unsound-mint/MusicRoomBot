from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EquipmentRequestRange(Base):
    __tablename__ = "equipment_request_ranges"
    __table_args__ = (
        Index("ix_equipment_request_ranges_request_id", "equipment_request_id"),
        Index("ix_equipment_request_ranges_start_at", "start_at"),
        Index("ix_equipment_request_ranges_end_at", "end_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipment_request_id: Mapped[int] = mapped_column(
        ForeignKey("equipment_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    equipment_request = relationship("EquipmentRequest", back_populates="ranges")
