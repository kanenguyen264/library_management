from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    Text,
    Enum,
    Index,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum

from app.core.db import Base


class ReportStatus(str, enum.Enum):
    """Trạng thái của báo cáo"""

    PENDING = "pending"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class ReportType(str, enum.Enum):
    """Loại báo cáo"""

    ABUSE = "abuse"
    SPAM = "spam"
    INAPPROPRIATE = "inappropriate"
    COPYRIGHT = "copyright"
    OTHER = "other"


class ReportEntityType(str, enum.Enum):
    """Đối tượng bị báo cáo"""

    USER = "user"
    BOOK = "book"
    REVIEW = "review"
    COMMENT = "comment"
    DISCUSSION = "discussion"
    CHAPTER = "chapter"
    BOOKSHELF = "bookshelf"
    ANNOTATION = "annotation"


class Report(Base):
    """Model lưu trữ báo cáo người dùng về nội dung vi phạm"""

    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_entity", "entity_type", "entity_id"),
        Index("ix_reports_status", "status"),
        Index("ix_reports_reporter_id", "reporter_id"),
        Index("ix_reports_handled_by", "handled_by"),
        Index("ix_reports_created_at", "created_at"),
        {"schema": "admin"},
    )

    id = Column(Integer, primary_key=True, index=True)
    reporter_id = Column(
        Integer, ForeignKey("user_data.users.id", ondelete="SET NULL"), nullable=True
    )
    entity_type = Column(Enum(ReportEntityType), nullable=False)
    entity_id = Column(Integer, nullable=False)
    report_type = Column(Enum(ReportType), nullable=False)
    status = Column(Enum(ReportStatus), default=ReportStatus.PENDING, nullable=False)
    description = Column(Text, nullable=True)
    admin_notes = Column(Text, nullable=True)
    handled_by = Column(
        Integer, ForeignKey("admin.admins.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    reporter = relationship(
        "User", foreign_keys=[reporter_id], backref="reports_submitted"
    )
    admin_handler = relationship(
        "Admin", foreign_keys=[handled_by], backref="handled_reports"
    )

    def __repr__(self):
        return f"<Report(id={self.id}, entity_type={self.entity_type}, entity_id={self.entity_id}, status={self.status})>"
