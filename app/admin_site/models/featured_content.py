from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import relationship
from app.core.db import Base


class FeaturedContent(Base):
    __tablename__ = "featured_content"
    __table_args__ = (
        Index("idx_featured_content_content_type", "content_type"),
        Index("idx_featured_content_content_id", "content_id"),
        Index("idx_featured_content_start_date", "start_date"),
        Index("idx_featured_content_end_date", "end_date"),
        {"schema": "admin"},
    )

    id = Column(Integer, primary_key=True)
    content_type = Column(String(100), nullable=False)
    content_id = Column(Integer, nullable=False)
    position = Column(Integer, default=0)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)
    created_by = Column(Integer, ForeignKey("admin.admins.id"), nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    admin = relationship("Admin", foreign_keys=[created_by])
