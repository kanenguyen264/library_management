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
from app.core.model_mixins import EventMixin


class Discussion(Base, EventMixin):
    __tablename__ = "discussions"
    __table_args__ = (
        Index("idx_discussions_book_id", "book_id"),
        Index("idx_discussions_chapter_id", "chapter_id"),
        Index("idx_discussions_user_id", "user_id"),
        Index("idx_discussions_is_pinned", "is_pinned"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, ForeignKey("public.books.id"), nullable=False)
    chapter_id = Column(Integer, ForeignKey("public.chapters.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    upvotes = Column(Integer, default=0)
    downvotes = Column(Integer, default=0)
    comments_count = Column(Integer, default=0)
    is_spoiler = Column(Boolean, default=False)
    is_pinned = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    book = relationship("Book", back_populates="discussions")
    chapter = relationship("Chapter", back_populates="discussions")
    user = relationship("User", back_populates="discussions")
    comments = relationship("DiscussionComment", back_populates="discussion")

    # Phương thức để phát hành sự kiện liên quan đến thảo luận
    def publish_discussion_event(self, event_type, **data):
        """
        Phát hành sự kiện liên quan đến thảo luận

        Args:
            event_type: Tên sự kiện
            **data: Dữ liệu bổ sung để gửi đến các subscriber

        Returns:
            int: Số lượng subscriber được thông báo
        """
        event_data = {
            "discussion_id": self.id,
            "book_id": self.book_id,
            "chapter_id": self.chapter_id,
            "user_id": self.user_id,
            **data,
        }
        return self.publish_event(event_type, **event_data)


class DiscussionComment(Base):
    __tablename__ = "discussion_comments"
    __table_args__ = (
        Index("idx_discussion_comments_discussion_id", "discussion_id"),
        Index("idx_discussion_comments_user_id", "user_id"),
        Index("idx_discussion_comments_parent_id", "parent_id"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    discussion_id = Column(
        Integer, ForeignKey("user_data.discussions.id"), nullable=False
    )
    user_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    parent_id = Column(
        Integer, ForeignKey("user_data.discussion_comments.id"), nullable=True
    )
    content = Column(Text, nullable=False)
    upvotes = Column(Integer, default=0)
    downvotes = Column(Integer, default=0)
    is_spoiler = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    discussion = relationship("Discussion", back_populates="comments")
    user = relationship("User", back_populates="discussion_comments")
    parent = relationship("DiscussionComment", remote_side=[id], backref="replies")
