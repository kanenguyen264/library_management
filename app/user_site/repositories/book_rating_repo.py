from typing import List, Optional, Dict, Any, Union, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc, and_, or_, not_
import logging

from app.user_site.models.book_rating import BookRating
from app.logging.setup import get_logger

logger = get_logger(__name__)


class BookRatingRepository:
    """
    Repository for book rating operations.
    """

    def __init__(self, db: Session):
        self.db = db

    async def create_rating(self, rating_data: Dict[str, Any]) -> BookRating:
        """
        Create a new book rating.

        Args:
            rating_data: Rating data dictionary

        Returns:
            Created BookRating
        """
        rating = BookRating(**rating_data)
        self.db.add(rating)
        self.db.commit()
        self.db.refresh(rating)
        return rating

    async def get_rating_by_id(self, rating_id: int) -> Optional[BookRating]:
        """
        Get a rating by ID.

        Args:
            rating_id: ID of the rating

        Returns:
            BookRating or None
        """
        return self.db.query(BookRating).filter(BookRating.id == rating_id).first()

    async def get_user_book_rating(
        self, user_id: int, book_id: int
    ) -> Optional[BookRating]:
        """
        Get a user's rating for a specific book.

        Args:
            user_id: User ID
            book_id: Book ID

        Returns:
            BookRating or None
        """
        return (
            self.db.query(BookRating)
            .filter(BookRating.user_id == user_id, BookRating.book_id == book_id)
            .first()
        )

    async def get_book_ratings(
        self,
        book_id: int,
        skip: int = 0,
        limit: int = 100,
        include_anonymous: bool = True,
        sort_by: str = "created_at",
        sort_desc: bool = True,
    ) -> List[BookRating]:
        """
        Get ratings for a book.

        Args:
            book_id: Book ID
            skip: Number of records to skip
            limit: Maximum number of records to return
            include_anonymous: Include anonymous ratings
            sort_by: Field to sort by
            sort_desc: Sort descending if True

        Returns:
            List of BookRating objects
        """
        query = self.db.query(BookRating).filter(BookRating.book_id == book_id)

        if not include_anonymous:
            query = query.filter(BookRating.is_anonymous == False)

        # Apply sorting
        if sort_by:
            sort_column = getattr(BookRating, sort_by, BookRating.created_at)
            if sort_desc:
                query = query.order_by(desc(sort_column))
            else:
                query = query.order_by(asc(sort_column))

        return query.offset(skip).limit(limit).all()

    async def count_book_ratings(
        self, book_id: int, include_anonymous: bool = True
    ) -> int:
        """
        Count ratings for a book.

        Args:
            book_id: Book ID
            include_anonymous: Include anonymous ratings

        Returns:
            Number of ratings
        """
        query = self.db.query(func.count(BookRating.id)).filter(
            BookRating.book_id == book_id
        )

        if not include_anonymous:
            query = query.filter(BookRating.is_anonymous == False)

        return query.scalar() or 0

    async def get_average_rating(self, book_id: int) -> float:
        """
        Get average rating for a book.

        Args:
            book_id: Book ID

        Returns:
            Average rating (0.0-5.0)
        """
        result = (
            self.db.query(func.avg(BookRating.rating))
            .filter(BookRating.book_id == book_id)
            .scalar()
        )

        return float(result) if result is not None else 0.0

    async def update_rating(
        self, rating_id: int, rating_data: Dict[str, Any]
    ) -> Optional[BookRating]:
        """
        Update a rating.

        Args:
            rating_id: Rating ID
            rating_data: Updated rating data

        Returns:
            Updated BookRating or None
        """
        rating = await self.get_rating_by_id(rating_id)
        if not rating:
            return None

        for key, value in rating_data.items():
            setattr(rating, key, value)

        self.db.commit()
        self.db.refresh(rating)
        return rating

    async def delete_rating(self, rating_id: int) -> bool:
        """
        Delete a rating.

        Args:
            rating_id: Rating ID

        Returns:
            True if deleted, False if not found
        """
        rating = await self.get_rating_by_id(rating_id)
        if not rating:
            return False

        self.db.delete(rating)
        self.db.commit()
        return True
