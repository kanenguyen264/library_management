from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    func,
)
from sqlalchemy.orm import relationship
from app.core.db import Base
from enum import Enum


class RecommendationType(str, Enum):
    PERSONALIZED = "PERSONALIZED"
    SIMILAR = "SIMILAR"
    TRENDING = "TRENDING"
    CATEGORY = "CATEGORY"
    AUTHOR = "AUTHOR"
    TAG = "TAG"
    NEW_RELEASE = "NEW_RELEASE"
    POPULAR = "POPULAR"
    EDITOR_PICK = "EDITOR_PICK"


class Recommendation(Base):
    __tablename__ = "reading_recommendations"
    __table_args__ = (
        Index("idx_reading_recommendations_user_id", "user_id"),
        Index("idx_reading_recommendations_book_id", "book_id"),
        Index("idx_reading_recommendations_type", "recommendation_type"),
        Index("idx_reading_recommendations_is_dismissed", "is_dismissed"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    book_id = Column(Integer, ForeignKey("public.books.id"), nullable=False)
    recommendation_type = Column(String(100), nullable=False)
    confidence_score = Column(Float, default=0.0)
    is_dismissed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="recommendations")
    book = relationship("Book", back_populates="recommendations")
