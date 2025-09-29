from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    Float,
    Date,
    DateTime,
    ForeignKey,
    Index,
    func,
    event,
)
from sqlalchemy.orm import relationship, validates
from app.core.db import Base
from app.core.model_mixins import (
    SoftDeleteMixin,
    CacheMixin,
    VersioningMixin,
    EventMixin,
)
from app.core.event import BookEvent
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Book(Base, SoftDeleteMixin, CacheMixin, VersioningMixin, EventMixin):
    __tablename__ = "books"
    __table_args__ = (
        Index("idx_books_isbn", "isbn"),
        Index("idx_books_title", "title"),
        Index("idx_books_is_published", "is_published"),
        Index("idx_books_popularity_score", "popularity_score"),
        Index("idx_books_is_featured", "is_featured"),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True)
    isbn = Column(String(20), unique=True, index=True)
    title = Column(String(255), nullable=False)
    subtitle = Column(String(255), nullable=True)
    publisher_id = Column(Integer, ForeignKey("public.publishers.id"), nullable=True)
    publication_date = Column(Date, nullable=True)
    language = Column(String(50), nullable=True)
    page_count = Column(Integer, nullable=True)
    cover_image_url = Column(String(500), nullable=True)
    cover_thumbnail_url = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    short_description = Column(Text, nullable=True)
    is_featured = Column(Boolean, default=False)
    is_published = Column(Boolean, default=False)
    avg_rating = Column(Float, default=0.0)
    review_count = Column(Integer, default=0)
    popularity_score = Column(Float, default=0.0)
    mature_content = Column(Boolean, default=False)

    # Relationships
    authors = relationship(
        "Author",
        secondary="public.books_authors",
        back_populates="books",
        lazy="joined",
    )
    categories = relationship(
        "Category",
        secondary="public.books_categories",
        back_populates="books",
        lazy="joined",
    )
    tags = relationship(
        "Tag", secondary="public.books_tags", back_populates="books", lazy="joined"
    )
    chapters = relationship("Chapter", back_populates="book", lazy="dynamic")
    series_items = relationship("BookSeriesItem", back_populates="book", lazy="dynamic")
    reading_histories = relationship(
        "ReadingHistory", back_populates="book", lazy="dynamic"
    )
    reading_sessions = relationship(
        "ReadingSession", back_populates="book", lazy="dynamic"
    )
    bookmarks = relationship("Bookmark", back_populates="book", lazy="dynamic")
    bookshelf_items = relationship(
        "BookshelfItem", back_populates="book", lazy="dynamic"
    )
    book_list_items = relationship(
        "UserBookListItem", back_populates="book", lazy="dynamic"
    )
    reviews = relationship("Review", back_populates="book", lazy="dynamic")
    annotations = relationship("Annotation", back_populates="book", lazy="dynamic")
    quotes = relationship("Quote", back_populates="book", lazy="dynamic")
    discussions = relationship("Discussion", back_populates="book", lazy="dynamic")
    recommendations = relationship(
        "Recommendation", back_populates="book", lazy="dynamic"
    )
    publisher = relationship("Publisher", back_populates="books", lazy="joined")

    # Validators
    @validates("isbn")
    def validate_isbn(self, key, isbn):
        """Validate ISBN format"""
        if isbn and len(isbn) not in [10, 13]:
            raise ValueError("ISBN must be 10 or 13 characters")
        return isbn

    # Business methods
    @classmethod
    def publish(cls, book_id):
        book = cls.query.get(book_id)
        if book:
            book.is_published = True
            book.date_published = datetime.now()
            db.session.commit()
            book.publish_book_event(BookEvent.PUBLISHED)
            return True
        return False

    @classmethod
    def unpublish(cls, book_id):
        book = cls.query.get(book_id)
        if book:
            book.is_published = False
            db.session.commit()
            book.publish_book_event(BookEvent.UNPUBLISHED)
            return True
        return False

    def update_popularity_score(self):
        """Update the popularity score based on various factors."""
        old_score = self.popularity_score

        # Calculate new score based on views, likes, ratings, etc.
        new_score = (
            (self.views or 0) * 0.4
            + (self.likes or 0) * 0.3
            + ((self.avg_rating or 0) * (self.rating_count or 0)) * 0.3
        )

        self.popularity_score = new_score
        db.session.commit()

        # Publish event if popularity changed significantly (20% change)
        if old_score > 0 and abs(new_score - old_score) / old_score > 0.2:
            self.publish_book_event(
                BookEvent.POPULARITY_CHANGED, old_score=old_score, new_score=new_score
            )

        return new_score

    def update_ratings(self, new_rating):
        """Update book rating statistics when a new rating is added."""
        old_rating = self.avg_rating
        old_count = self.rating_count or 0

        # Update rating count and recalculate average
        self.rating_count = old_count + 1
        self.avg_rating = (
            (old_rating or 0) * old_count + new_rating
        ) / self.rating_count
        db.session.commit()

        # Publish event if rating changed significantly (0.5 points) or we hit certain thresholds
        if (
            old_count == 0
            or abs(self.avg_rating - old_rating) >= 0.5
            or self.rating_count in [10, 50, 100, 500, 1000]
        ):
            self.publish_book_event(
                BookEvent.RATING_CHANGED,
                old_rating=old_rating,
                new_rating=self.avg_rating,
                rating_count=self.rating_count,
            )

        return self.avg_rating

    def publish_book_event(self, event_type, **data):
        """
        Phát hành sự kiện liên quan đến sách với loại sự kiện và dữ liệu đã cho.

        Args:
            event_type: Một trong các sự kiện được định nghĩa trong BookEvent
            **data: Dữ liệu bổ sung để gửi đến các subscriber

        Returns:
            int: Số lượng subscriber được thông báo
        """
        from app.core.event import publish_book_event

        return publish_book_event(event_type, self.id, **data)


class BookAuthor(Base):
    __tablename__ = "books_authors"
    __table_args__ = (
        Index("idx_books_authors_book_id", "book_id"),
        Index("idx_books_authors_author_id", "author_id"),
        {"schema": "public"},
    )

    book_id = Column(Integer, ForeignKey("public.books.id"), primary_key=True)
    author_id = Column(Integer, ForeignKey("public.authors.id"), primary_key=True)


class BookTag(Base):
    __tablename__ = "books_tags"
    __table_args__ = (
        Index("idx_books_tags_book_id", "book_id"),
        Index("idx_books_tags_tag_id", "tag_id"),
        {"schema": "public"},
    )

    book_id = Column(Integer, ForeignKey("public.books.id"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("public.tags.id"), primary_key=True)
