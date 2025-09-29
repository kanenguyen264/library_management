from sqlalchemy import Column, Integer, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import relationship
from app.core.db import Base


class UserAchievement(Base):
    __tablename__ = "user_achievements"
    __table_args__ = (
        Index("idx_user_achievements_user_id", "user_id"),
        Index("idx_user_achievements_achievement_id", "achievement_id"),
        Index("idx_user_achievements_earned_at", "earned_at"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    achievement_id = Column(
        Integer, ForeignKey("admin.achievements.id"), nullable=False
    )
    earned_at = Column(DateTime, nullable=False)
    # created_at được thừa kế từ CustomBase

    # Relationships
    user = relationship("User", back_populates="achievements")
    achievement = relationship("Achievement", foreign_keys=[achievement_id])
