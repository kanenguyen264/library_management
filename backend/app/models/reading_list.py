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


class ReadingList(Base):
    __tablename__ = "reading_lists"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    is_public = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # Foreign Keys with proper cascade deletion
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="reading_lists")
    items = relationship(
        "ReadingListItem", back_populates="reading_list", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return (
            f"<ReadingList(id={self.id}, name='{self.name}', user_id={self.user_id})>"
        )


class ReadingListItem(Base):
    __tablename__ = "reading_list_items"

    id = Column(Integer, primary_key=True, index=True)

    # Foreign Keys with proper cascade deletion
    reading_list_id = Column(
        Integer,
        ForeignKey("reading_lists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    book_id = Column(
        Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Order within the reading list
    order_index = Column(Integer, default=0)

    # Optional notes for this book in the list
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    reading_list = relationship("ReadingList", back_populates="items")
    book = relationship("Book", back_populates="reading_list_items")

    # Constraints - One book per reading list (no duplicates)
    __table_args__ = (
        UniqueConstraint(
            "reading_list_id", "book_id", name="unique_book_per_reading_list"
        ),
    )

    def __repr__(self):
        return f"<ReadingListItem(id={self.id}, reading_list_id={self.reading_list_id}, book_id={self.book_id})>"
