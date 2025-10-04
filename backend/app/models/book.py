from sqlalchemy import (
    Boolean,
    Column,
    Date,
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


class Book(Base):
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    isbn = Column(String, nullable=True, unique=True)
    description = Column(Text, nullable=True)
    publication_date = Column(Date, nullable=True)
    pages = Column(Integer, nullable=True)
    language = Column(String, nullable=True)
    cover_url = Column(String, nullable=True)
    pdf_url = Column(String, nullable=True)
    epub_url = Column(String, nullable=True)
    price = Column(Float, nullable=True)
    is_free = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # Foreign Keys
    author_id = Column(Integer, ForeignKey("authors.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    author = relationship("Author", back_populates="books")
    category = relationship("Category", back_populates="books")
    reading_progress = relationship(
        "ReadingProgress", back_populates="book", cascade="all, delete-orphan"
    )
    chapters = relationship(
        "Chapter", back_populates="book", cascade="all, delete-orphan"
    )
    favorites = relationship(
        "Favorite", back_populates="book", cascade="all, delete-orphan"
    )
    reading_list_items = relationship(
        "ReadingListItem", back_populates="book", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Book(id={self.id}, title='{self.title}')>"
