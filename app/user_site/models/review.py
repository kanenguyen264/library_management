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
import enum
from app.core.db import Base
from app.core.model_mixins import EventMixin


class ReviewStatus(str, enum.Enum):
    """Trạng thái của đánh giá sách"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    FLAGGED = "flagged"


class Review(Base, EventMixin):
    __tablename__ = "reviews"
    __table_args__ = (
        Index("idx_reviews_user_id", "user_id"),
        Index("idx_reviews_book_id", "book_id"),
        Index("idx_reviews_rating", "rating"),
        Index("idx_reviews_is_approved", "is_approved"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    book_id = Column(Integer, ForeignKey("public.books.id"), nullable=False)
    rating = Column(Integer, nullable=False)
    title = Column(String(255), nullable=True)
    comment = Column(Text, nullable=True)
    likes_count = Column(Integer, default=0)
    reports_count = Column(Integer, default=0)
    is_spoiler = Column(Boolean, default=False)
    is_verified_purchase = Column(Boolean, default=False)
    is_approved = Column(Boolean, default=True)
    status = Column(String(50), default=ReviewStatus.APPROVED)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="reviews")
    book = relationship("Book", back_populates="reviews")
    likes = relationship("ReviewLike", back_populates="review")
    reports = relationship("ReviewReport", back_populates="review")

    # Phương thức để phát hành sự kiện liên quan đến đánh giá
    def publish_review_event(self, event_type, **data):
        """
        Phát hành sự kiện liên quan đến đánh giá sách

        Args:
            event_type: Tên sự kiện
            **data: Dữ liệu bổ sung để gửi đến các subscriber

        Returns:
            int: Số lượng subscriber được thông báo
        """
        event_data = {
            "review_id": self.id,
            "book_id": self.book_id,
            "user_id": self.user_id,
            "rating": self.rating,
            **data,
        }
        return self.publish_event(event_type, **event_data)


class ReviewLike(Base):
    __tablename__ = "review_likes"
    __table_args__ = (
        Index("idx_review_likes_review_id", "review_id"),
        Index("idx_review_likes_user_id", "user_id"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    review_id = Column(Integer, ForeignKey("user_data.reviews.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    review = relationship("Review", back_populates="likes")
    user = relationship("User", back_populates="review_likes")


class ReviewReport(Base):
    __tablename__ = "review_reports"
    __table_args__ = (
        Index("idx_review_reports_review_id", "review_id"),
        Index("idx_review_reports_reporter_id", "reporter_id"),
        Index("idx_review_reports_status", "status"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    review_id = Column(Integer, ForeignKey("user_data.reviews.id"), nullable=False)
    reporter_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    reason = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default=ReviewStatus.PENDING)
    resolved_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=func.now())
    resolved_at = Column(DateTime, nullable=True)

    # Relationships
    review = relationship("Review", back_populates="reports")
    reporter = relationship(
        "User", foreign_keys=[reporter_id], back_populates="review_reports"
    )
