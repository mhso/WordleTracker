from datetime import datetime, date
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import Date, ForeignKey, String, Integer, DateTime
from sqlalchemy.orm import mapped_column, Mapped, relationship
from sqlalchemy.orm.decl_api import DeclarativeBase

class Environment(Enum):
    DEVELOPMENT = "dev"
    PRODUCTION = "prod"

class Base(DeclarativeBase):
    pass

class Day(Base):
    __tablename__ = "days"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    word: Mapped[str] = mapped_column(String)
    day: Mapped[int] = mapped_column(Integer)
    date: Mapped["date"] = mapped_column(Date)

    scores = relationship("Score", back_populates="day", cascade="all, delete", order_by="Score.disc_id.asc()")

    def get_score_entry(self, disc_id: int):
        return next(filter(lambda s: s.disc_id == disc_id, self.scores), None)

class Score(Base):
    __tablename__ = "scores"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    day_id: Mapped[str] = mapped_column(String(64), ForeignKey("days.id", ondelete="CASCADE"))
    disc_id: Mapped[int] = mapped_column(Integer)
    score: Mapped[Optional[int]] = mapped_column(Integer)
    message_id: Mapped[int] = mapped_column(Integer)
    date_started: Mapped[datetime] = mapped_column(DateTime)
    date_finished: Mapped[Optional[datetime]] = mapped_column(DateTime)

    day = relationship("Day", back_populates="scores")

class FakeWord(Base):
    __tablename__ = "fake_words"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    day_id: Mapped[str] = mapped_column(String(64), ForeignKey("days.id", ondelete="CASCADE"))
    reported_by: Mapped[int] = mapped_column(Integer)
    load_time: Mapped[Optional[datetime]] = mapped_column(DateTime, default=lambda: datetime.now())
