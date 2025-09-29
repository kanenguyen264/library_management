from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index, func, Text
from sqlalchemy.orm import relationship
from app.core.db import Base


class ReadingSession(Base):
    __tablename__ = "reading_sessions"
    __table_args__ = (
        Index("idx_reading_sessions_user_id", "user_id"),
        Index("idx_reading_sessions_book_id", "book_id"),
        Index("idx_reading_sessions_start_time", "start_time"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    book_id = Column(Integer, ForeignKey("public.books.id"), nullable=False)
    chapter_id = Column(Integer, ForeignKey("public.chapters.id"), nullable=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    start_position = Column(String(50), nullable=True)
    end_position = Column(String(50), nullable=True)
    device_info = Column(String(255), nullable=True)
    ip_address = Column(String(50), nullable=True)
    pages_read = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="reading_sessions")
    book = relationship("Book", back_populates="reading_sessions")
    chapter = relationship("Chapter", back_populates="reading_sessions")
