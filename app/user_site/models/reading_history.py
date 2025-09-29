from sqlalchemy import (
    Column,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    func,
    String,
)
from sqlalchemy.orm import relationship
from app.core.db import Base
from app.core.model_mixins import EventMixin


class ReadingHistory(Base, EventMixin):
    __tablename__ = "reading_history"
    __table_args__ = (
        Index("idx_reading_history_user_id", "user_id"),
        Index("idx_reading_history_book_id", "book_id"),
        Index("idx_reading_history_chapter_id", "chapter_id"),
        Index("idx_reading_history_is_completed", "is_completed"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    book_id = Column(Integer, ForeignKey("public.books.id"), nullable=False)
    chapter_id = Column(Integer, ForeignKey("public.chapters.id"), nullable=True)
    progress_percentage = Column(Float, default=0.0)
    last_position = Column(String(50), nullable=True)
    time_spent_seconds = Column(Integer, default=0)
    is_completed = Column(Boolean, default=False)
    last_read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="reading_histories")
    book = relationship("Book", back_populates="reading_histories")
    chapter = relationship("Chapter", back_populates="reading_histories")

    # Phương thức để phát hành sự kiện liên quan đến lịch sử đọc
    def publish_reading_event(self, event_type, **data):
        """
        Phát hành sự kiện liên quan đến lịch sử đọc sách

        Args:
            event_type: Tên sự kiện
            **data: Dữ liệu bổ sung để gửi đến các subscriber

        Returns:
            int: Số lượng subscriber được thông báo
        """
        event_data = {
            "reading_history_id": self.id,
            "book_id": self.book_id,
            "user_id": self.user_id,
            "chapter_id": self.chapter_id,
            "progress_percentage": self.progress_percentage,
            "is_completed": self.is_completed,
            **data,
        }
        return self.publish_event(event_type, **event_data)
