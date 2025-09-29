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


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        Index("idx_categories_slug", "slug"),
        Index("idx_categories_parent_id", "parent_id"),
        Index("idx_categories_is_active", "is_active"),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    icon = Column(String(255), nullable=True)
    parent_id = Column(Integer, ForeignKey("public.categories.id"), nullable=True)
    display_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    parent = relationship("Category", remote_side=[id], backref="children")
    books = relationship(
        "Book", secondary="public.books_categories", back_populates="categories"
    )


class BookCategory(Base):
    __tablename__ = "books_categories"
    __table_args__ = (
        Index("idx_books_categories_book_id", "book_id"),
        Index("idx_books_categories_category_id", "category_id"),
        {"schema": "public"},
    )

    book_id = Column(Integer, ForeignKey("public.books.id"), primary_key=True)
    category_id = Column(Integer, ForeignKey("public.categories.id"), primary_key=True)
    created_at = Column(DateTime, default=func.now())
