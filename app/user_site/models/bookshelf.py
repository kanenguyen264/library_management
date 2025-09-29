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


class Bookshelf(Base):
    __tablename__ = "bookshelves"
    __table_args__ = (
        Index("idx_bookshelves_user_id", "user_id"),
        Index("idx_bookshelves_is_public", "is_public"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_public = Column(Boolean, default=True)
    cover_image = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="bookshelves")
    items = relationship("BookshelfItem", back_populates="bookshelf")


class BookshelfItem(Base):
    __tablename__ = "bookshelf_items"
    __table_args__ = (
        Index("idx_bookshelf_items_bookshelf_id", "bookshelf_id"),
        Index("idx_bookshelf_items_book_id", "book_id"),
        Index("idx_bookshelf_items_added_at", "added_at"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    bookshelf_id = Column(
        Integer, ForeignKey("user_data.bookshelves.id"), nullable=False
    )
    book_id = Column(Integer, ForeignKey("public.books.id"), nullable=False)
    added_at = Column(DateTime, default=func.now())
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    bookshelf = relationship("Bookshelf", back_populates="items")
    book = relationship("Book", back_populates="bookshelf_items")
