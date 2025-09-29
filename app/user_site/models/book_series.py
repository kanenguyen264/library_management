from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import relationship
from app.core.db import Base


class BookSeries(Base):
    __tablename__ = "book_series"
    __table_args__ = (Index("idx_book_series_name", "name"), {"schema": "public"})

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    cover_image = Column(String(500), nullable=True)
    total_books = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    items = relationship("BookSeriesItem", back_populates="series")


class BookSeriesItem(Base):
    __tablename__ = "book_series_items"
    __table_args__ = (
        Index("idx_book_series_items_series_id", "series_id"),
        Index("idx_book_series_items_book_id", "book_id"),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True)
    series_id = Column(Integer, ForeignKey("public.book_series.id"), nullable=False)
    book_id = Column(Integer, ForeignKey("public.books.id"), nullable=False)
    position = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    series = relationship("BookSeries", back_populates="items")
    book = relationship("Book", back_populates="series_items")
