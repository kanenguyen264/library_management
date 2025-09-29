from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Index, func
from sqlalchemy.orm import relationship
from app.core.db import Base


class Badge(Base):
    __tablename__ = "badges"
    __table_args__ = (
        Index("idx_badges_name", "name"),
        Index("idx_badges_is_featured", "is_featured"),
        {"schema": "admin"},
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    icon_url = Column(String(500), nullable=True)
    criteria = Column(Text, nullable=True)
    is_featured = Column(Boolean, default=False)
    # created_at và updated_at được thừa kế từ CustomBase

    # Relationships
    user_badges = relationship("UserBadge", back_populates="badge")
