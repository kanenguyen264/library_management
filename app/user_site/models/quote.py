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


class Quote(Base):
    __tablename__ = "quotes"
    __table_args__ = (
        Index("idx_quotes_user_id", "user_id"),
        Index("idx_quotes_book_id", "book_id"),
        Index("idx_quotes_chapter_id", "chapter_id"),
        Index("idx_quotes_is_public", "is_public"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    book_id = Column(Integer, ForeignKey("public.books.id"), nullable=False)
    chapter_id = Column(Integer, ForeignKey("public.chapters.id"), nullable=True)
    content = Column(Text, nullable=False)
    start_offset = Column(String(50), nullable=True)
    end_offset = Column(String(50), nullable=True)
    likes_count = Column(Integer, default=0)
    shares_count = Column(Integer, default=0)
    is_public = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="quotes")
    book = relationship("Book", back_populates="quotes")
    chapter = relationship("Chapter", back_populates="quotes")
    likes = relationship("QuoteLike", back_populates="quote")


class QuoteLike(Base):
    __tablename__ = "quote_likes"
    __table_args__ = (
        Index("idx_quote_likes_quote_id", "quote_id"),
        Index("idx_quote_likes_user_id", "user_id"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    quote_id = Column(Integer, ForeignKey("user_data.quotes.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    quote = relationship("Quote", back_populates="likes")
    user = relationship("User", back_populates="quote_likes")
