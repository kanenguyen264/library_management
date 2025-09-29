from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    Boolean,
    ForeignKey,
    Text,
    DateTime,
    Index,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.common.db.base_class import Base


class BookRating(Base):
    """
    Book rating model.
    """

    __tablename__ = "book_ratings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    book_id = Column(
        Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    rating = Column(Integer, nullable=False)  # 1-5 stars
    review = Column(Text, nullable=True)
    is_anonymous = Column(Boolean, default=False)
    is_verified_purchase = Column(Boolean, default=False)
    helpful_count = Column(Integer, default=0)
    report_count = Column(Integer, default=0)
    status = Column(String(20), default="active")  # active, hidden, deleted
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="book_ratings")
    book = relationship("Book", back_populates="ratings")

    # Indexes for efficient queries
    __table_args__ = (
        Index("idx_book_ratings_user_id", "user_id"),
        Index("idx_book_ratings_book_id", "book_id"),
        Index("idx_book_ratings_created_at", "created_at"),
        Index("idx_book_ratings_rating", "rating"),
        Index("uq_book_ratings_user_book", "user_id", "book_id", unique=True),
    )

    def __repr__(self):
        return f"<BookRating(id={self.id}, user_id={self.user_id}, book_id={self.book_id}, rating={self.rating})>"
