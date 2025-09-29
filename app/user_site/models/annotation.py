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


class Annotation(Base):
    __tablename__ = "annotations"
    __table_args__ = (
        Index("idx_annotations_user_id", "user_id"),
        Index("idx_annotations_book_id", "book_id"),
        Index("idx_annotations_chapter_id", "chapter_id"),
        Index("idx_annotations_is_public", "is_public"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    book_id = Column(Integer, ForeignKey("public.books.id"), nullable=False)
    chapter_id = Column(Integer, ForeignKey("public.chapters.id"), nullable=True)
    start_offset = Column(String(50), nullable=False)
    end_offset = Column(String(50), nullable=False)
    highlighted_text = Column(Text, nullable=False)
    note = Column(Text, nullable=True)
    color = Column(String(20), nullable=True)
    is_public = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="annotations")
    book = relationship("Book", back_populates="annotations")
    chapter = relationship("Chapter", back_populates="annotations")
