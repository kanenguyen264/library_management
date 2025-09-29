from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import relationship
from app.core.db import Base


class ContentApprovalQueue(Base):
    __tablename__ = "content_approval_queue"
    __table_args__ = (
        Index("idx_content_approval_content_type", "content_type"),
        Index("idx_content_approval_content_id", "content_id"),
        Index("idx_content_approval_status", "status"),
        Index("idx_content_approval_submitted_by", "submitted_by"),
        {"schema": "admin"},
    )

    id = Column(Integer, primary_key=True)
    content_type = Column(String(100), nullable=False)
    content_id = Column(Integer, nullable=False)
    submitted_by = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    status = Column(String(50), default="pending")
    reviewer_id = Column(Integer, ForeignKey("admin.admins.id"), nullable=True)
    review_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    submitter = relationship("User", foreign_keys=[submitted_by])
    reviewer = relationship("Admin", foreign_keys=[reviewer_id])
