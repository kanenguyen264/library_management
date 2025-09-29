from sqlalchemy import Column, Integer, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import relationship
from app.core.db import Base


class UserBadge(Base):
    __tablename__ = "user_badges"
    __table_args__ = (
        Index("idx_user_badges_user_id", "user_id"),
        Index("idx_user_badges_badge_id", "badge_id"),
        Index("idx_user_badges_earned_at", "earned_at"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    badge_id = Column(Integer, ForeignKey("admin.badges.id"), nullable=False)
    earned_at = Column(DateTime, nullable=False)
    # created_at được thừa kế từ CustomBase

    # Relationships
    user = relationship("User", back_populates="badges")
    badge = relationship("Badge", foreign_keys=[badge_id])
