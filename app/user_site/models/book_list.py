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


class UserBookList(Base):
    __tablename__ = "user_book_lists"
    __table_args__ = (
        Index("idx_user_book_lists_user_id", "user_id"),
        Index("idx_user_book_lists_is_public", "is_public"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_public = Column(Boolean, default=True)
    cover_image = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="book_lists")
    items = relationship("UserBookListItem", back_populates="list")


class UserBookListItem(Base):
    __tablename__ = "user_book_list_items"
    __table_args__ = (
        Index("idx_user_book_list_items_list_id", "list_id"),
        Index("idx_user_book_list_items_book_id", "book_id"),
        Index("idx_user_book_list_items_position", "position"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    list_id = Column(
        Integer, ForeignKey("user_data.user_book_lists.id"), nullable=False
    )
    book_id = Column(Integer, ForeignKey("public.books.id"), nullable=False)
    position = Column(Integer, default=0)
    added_at = Column(DateTime, default=func.now())
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    list = relationship("UserBookList", back_populates="items")
    book = relationship("Book", back_populates="book_list_items")
