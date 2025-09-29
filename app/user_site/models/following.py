from sqlalchemy import (
    Column,
    Integer,
    DateTime,
    ForeignKey,
    PrimaryKeyConstraint,
    Index,
    func,
)
from sqlalchemy.orm import relationship
from app.core.db import Base


class UserFollowing(Base):
    __tablename__ = "user_following"
    __table_args__ = (
        PrimaryKeyConstraint("follower_id", "following_id"),
        Index("idx_user_following_follower_id", "follower_id"),
        Index("idx_user_following_following_id", "following_id"),
        {"schema": "user_data"},
    )

    follower_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    following_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    follower = relationship(
        "User", foreign_keys=[follower_id], back_populates="following"
    )
    following = relationship(
        "User", foreign_keys=[following_id], back_populates="followers"
    )
