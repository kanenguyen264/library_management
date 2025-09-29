from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index, func, Text
from sqlalchemy.orm import relationship
from app.core.db import Base


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        Index("idx_tags_slug", "slug"),
        Index("idx_tags_name", "name"),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    color = Column(String(7), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    books = relationship("Book", secondary="public.books_tags", back_populates="tags")


class BookTag(Base):
    __tablename__ = "books_tags"
    __table_args__ = (
        Index("idx_books_tags_book_id", "book_id"),
        Index("idx_books_tags_tag_id", "tag_id"),
        {"schema": "public", "extend_existing": True},
    )

    book_id = Column(Integer, ForeignKey("public.books.id"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("public.tags.id"), primary_key=True)
    created_at = Column(DateTime, default=func.now())
