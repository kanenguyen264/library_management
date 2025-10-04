from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class ReadingProgress(Base):
    __tablename__ = "reading_progress"

    id = Column(Integer, primary_key=True, index=True)

    # Foreign Keys with proper cascade deletion
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    book_id = Column(
        Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )

    # Progress tracking
    current_page = Column(Integer, default=0)
    total_pages = Column(Integer, nullable=True)
    progress_percentage = Column(Float, default=0.0)
    reading_time_minutes = Column(Integer, default=0)

    # Status
    status = Column(
        String, default="not_started"
    )  # not_started, reading, completed, dropped
    is_completed = Column(Boolean, default=False)

    # Timestamps
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    last_read_at = Column(DateTime(timezone=True), nullable=True)

    # Notes
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="reading_progress")
    book = relationship("Book", back_populates="reading_progress")

    def __repr__(self):
        return f"<ReadingProgress(id={self.id}, user_id={self.user_id}, book_id={self.book_id}, progress={self.progress_percentage}%)>"
