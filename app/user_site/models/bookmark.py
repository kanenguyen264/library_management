from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import relationship
from app.core.db import Base


class Bookmark(Base):
    __tablename__ = "bookmarks"
    __table_args__ = (
        Index("idx_bookmarks_user_id", "user_id"),
        Index("idx_bookmarks_book_id", "book_id"),
        Index("idx_bookmarks_chapter_id", "chapter_id"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    book_id = Column(Integer, ForeignKey("public.books.id"), nullable=False)
    chapter_id = Column(Integer, ForeignKey("public.chapters.id"), nullable=True)
    position_offset = Column(String(50), nullable=False)
    title = Column(String(255), nullable=True)
    note = Column(Text, nullable=True)
    color = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="bookmarks")
    book = relationship("Book", back_populates="bookmarks")
    chapter = relationship("Chapter", back_populates="bookmarks")
