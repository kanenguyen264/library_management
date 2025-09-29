from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    func,
)
from sqlalchemy.orm import relationship
from app.core.db import Base
from enum import Enum


class GoalType(str, Enum):
    BOOKS = "BOOKS"
    PAGES = "PAGES"
    MINUTES = "MINUTES"
    CHAPTERS = "CHAPTERS"


class GoalStatus(str, Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class ReadingGoal(Base):
    __tablename__ = "reading_goals"
    __table_args__ = (
        Index("idx_reading_goals_user_id", "user_id"),
        Index("idx_reading_goals_goal_type", "goal_type"),
        Index("idx_reading_goals_is_completed", "is_completed"),
        Index("idx_reading_goals_end_date", "end_date"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    goal_type = Column(String(50), nullable=False)
    target_value = Column(Float, nullable=False)
    current_value = Column(Float, default=0)
    period = Column(String(50), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="reading_goals")
    progress = relationship("ReadingGoalProgress", back_populates="goal")


class ReadingGoalProgress(Base):
    __tablename__ = "reading_goal_progress"
    __table_args__ = (
        Index("idx_reading_goal_progress_goal_id", "goal_id"),
        Index("idx_reading_goal_progress_date", "date"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    goal_id = Column(Integer, ForeignKey("user_data.reading_goals.id"), nullable=False)
    date = Column(Date, nullable=False)
    progress_value = Column(Float, nullable=False)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    goal = relationship("ReadingGoal", back_populates="progress")
