from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Date,
    DateTime,
    ForeignKey,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.core.db import Base


class Author(Base):
    __tablename__ = "authors"
    __table_args__ = (
        Index("idx_authors_name", "name"),
        Index("idx_authors_country", "country"),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    biography = Column(Text, nullable=True)
    photo_url = Column(String(500), nullable=True)
    birthdate = Column(Date, nullable=True)
    country = Column(String(100), nullable=True)
    website = Column(String(255), nullable=True)
    social_media_links = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    books = relationship(
        "Book", secondary="public.book_authors", back_populates="authors"
    )


class BookAuthor(Base):
    __tablename__ = "book_authors"
    __table_args__ = (
        Index("idx_book_authors_book_id", "book_id"),
        Index("idx_book_authors_author_id", "author_id"),
        {"schema": "public"},
    )

    book_id = Column(Integer, ForeignKey("public.books.id"), primary_key=True)
    author_id = Column(Integer, ForeignKey("public.authors.id"), primary_key=True)
    role = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=func.now())
