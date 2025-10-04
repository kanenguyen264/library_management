from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Favorite(Base):
    __tablename__ = "favorites"

    id = Column(Integer, primary_key=True, index=True)

    # Foreign Keys with proper cascade deletion
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    book_id = Column(
        Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="favorites")
    book = relationship("Book", back_populates="favorites")

    # Constraints - One favorite per user per book
    __table_args__ = (
        UniqueConstraint("user_id", "book_id", name="unique_user_book_favorite"),
    )

    def __repr__(self):
        return (
            f"<Favorite(id={self.id}, user_id={self.user_id}, book_id={self.book_id})>"
        )
