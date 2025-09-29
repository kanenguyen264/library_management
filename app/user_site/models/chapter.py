from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    func,
)
from sqlalchemy.orm import relationship
from app.core.db import Base
from app.core.model_mixins import EventMixin


class Chapter(Base, EventMixin):
    __tablename__ = "chapters"
    __table_args__ = (
        Index("idx_chapters_book_id", "book_id"),
        Index("idx_chapters_chapter_number", "number"),
        Index("idx_chapters_is_published", "is_published"),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(
        Integer, ForeignKey("public.books.id", ondelete="CASCADE"), nullable=False
    )
    number = Column(Integer, nullable=False, comment="Số thứ tự chương")
    title = Column(String(255), nullable=False)
    subtitle = Column(String(255), nullable=True)
    content = Column(Text, nullable=True)
    preview_text = Column(Text, nullable=True)
    status = Column(String(20), default="draft", nullable=False)
    scheduled_publish_time = Column(DateTime(timezone=True), nullable=True)
    word_count = Column(Integer, nullable=True)
    estimated_read_time = Column(Integer, nullable=True)
    is_free = Column(Boolean, default=False, nullable=False)
    is_published = Column(Boolean, default=False)
    view_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    book = relationship("Book", back_populates="chapters")
    media = relationship(
        "ChapterMedia", back_populates="chapter", cascade="all, delete-orphan"
    )
    reading_histories = relationship("ReadingHistory", back_populates="chapter")
    reading_sessions = relationship("ReadingSession", back_populates="chapter")
    bookmarks = relationship("Bookmark", back_populates="chapter")
    annotations = relationship("Annotation", back_populates="chapter")
    quotes = relationship("Quote", back_populates="chapter")
    discussions = relationship("Discussion", back_populates="chapter")

    # Phương thức để phát hành sự kiện liên quan đến chương
    def publish_chapter_event(self, event_type, **data):
        """
        Phát hành sự kiện liên quan đến chương sách

        Args:
            event_type: Tên sự kiện từ lớp ChapterEvent
            **data: Dữ liệu bổ sung để gửi đến các subscriber

        Returns:
            int: Số lượng subscriber được thông báo
        """
        from app.core.event import publish_chapter_event

        return publish_chapter_event(event_type, self.id, book_id=self.book_id, **data)


class ChapterMedia(Base):
    """
    Model lưu trữ media (hình ảnh, audio, video) cho chương sách.
    """

    __tablename__ = "chapter_media"
    __table_args__ = (
        Index("idx_chapter_media_chapter_id", "chapter_id"),
        Index("idx_chapter_media_type", "media_type"),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True, index=True)
    chapter_id = Column(
        Integer, ForeignKey("public.chapters.id", ondelete="CASCADE"), nullable=False
    )
    media_type = Column(String(20), nullable=False, comment="image, audio, video")
    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    url = Column(String(500), nullable=False)
    storage_path = Column(String(500), nullable=True)
    thumbnail_url = Column(String(500), nullable=True)
    position = Column(Integer, default=0, nullable=False, comment="Vị trí hiển thị")
    metadata_json = Column(Text, nullable=True, comment="JSON metadata")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    chapter = relationship("Chapter", back_populates="media")
