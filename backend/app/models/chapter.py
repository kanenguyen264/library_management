from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Chapter(Base):
    __tablename__ = "chapters"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=True)
    chapter_number = Column(Integer, nullable=False, index=True)
    image_url = Column(String, nullable=True)
    is_published = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # Foreign Keys with proper cascade deletion
    book_id = Column(
        Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    book = relationship("Book", back_populates="chapters")

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "book_id", "chapter_number", name="unique_chapter_number_per_book"
        ),
    )

    def __repr__(self):
        return f"<Chapter(id={self.id}, title='{self.title}', chapter_number={self.chapter_number})>"
