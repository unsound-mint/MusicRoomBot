# app/models/config_model.py
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Config(Base):
    __tablename__ = "config"

    key: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
