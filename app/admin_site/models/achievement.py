from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.core.db import Base


class Achievement(Base):
    __tablename__ = "achievements"
    __table_args__ = (
        Index("idx_achievements_name", "name"),
        Index("idx_achievements_difficulty_level", "difficulty_level"),
        Index("idx_achievements_is_active", "is_active"),
        {"schema": "admin"},
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    icon_url = Column(String(500), nullable=True)
    criteria_json = Column(JSONB, nullable=True)
    points = Column(Integer, default=0)
    difficulty_level = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)

    # Relationships
    user_achievements = relationship("UserAchievement", back_populates="achievement")
