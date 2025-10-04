from datetime import datetime
from typing import List, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload

from app.crud.base import CRUDBase
from app.models.book import Book
from app.models.favorite import Favorite
from app.models.user import User
from app.schemas.favorite import FavoriteCreate, FavoriteUpdate


class CRUDFavorite(CRUDBase[Favorite, FavoriteCreate, FavoriteUpdate]):
    def get_by_user_and_book(
        self, db: Session, *, user_id: int, book_id: int
    ) -> Optional[Favorite]:
        return (
            db.query(Favorite)
            .filter(Favorite.user_id == user_id, Favorite.book_id == book_id)
            .first()
        )

    def get_by_user(
        self, db: Session, *, user_id: int, skip: int = 0, limit: int = 10000
    ) -> List[Favorite]:
        return (
            db.query(Favorite)
            .filter(Favorite.user_id == user_id)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_user_with_details(
        self, db: Session, *, user_id: int, skip: int = 0, limit: int = 10000
    ) -> List[Favorite]:
        """Get favorites with book details"""
        return (
            db.query(Favorite)
            .options(joinedload(Favorite.book))
            .filter(Favorite.user_id == user_id)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_with_details(self, db: Session, *, id: int) -> Optional[Favorite]:
        """Get favorite with book details"""
        return (
            db.query(Favorite)
            .options(joinedload(Favorite.book))
            .filter(Favorite.id == id)
            .first()
        )

    def create_favorite(self, db: Session, *, user_id: int, book_id: int) -> Favorite:
        """Create a new favorite"""
        favorite = Favorite(user_id=user_id, book_id=book_id)
        db.add(favorite)
        db.commit()
        db.refresh(favorite)
        return favorite

    def remove_favorite(
        self, db: Session, *, user_id: int, book_id: int
    ) -> Optional[Favorite]:
        """Remove a favorite"""
        favorite = self.get_by_user_and_book(db, user_id=user_id, book_id=book_id)
        if favorite:
            db.delete(favorite)
            db.commit()
            return favorite
        return None

    def toggle_favorite(
        self, db: Session, *, user_id: int, book_id: int
    ) -> tuple[Optional[Favorite], bool]:
        """Toggle favorite status"""
        favorite = self.get_by_user_and_book(db, user_id=user_id, book_id=book_id)
        if favorite:
            # Remove favorite
            db.delete(favorite)
            db.commit()
            return favorite, False
        else:
            # Add favorite
            favorite = self.create_favorite(db, user_id=user_id, book_id=book_id)
            return favorite, True

    def is_favorited(self, db: Session, *, user_id: int, book_id: int) -> bool:
        """Check if book is favorited by user"""
        return (
            self.get_by_user_and_book(db, user_id=user_id, book_id=book_id) is not None
        )

    def get_user_favorites_count(self, db: Session, *, user_id: int) -> int:
        """Get total favorites count for user"""
        return db.query(Favorite).filter(Favorite.user_id == user_id).count()

    def get_multi_with_filters(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 10000,
        search: Optional[str] = None,
        user_id: Optional[int] = None,
        book_id: Optional[int] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
    ) -> List[Favorite]:
        """Get favorites with comprehensive filtering and search (Admin only)"""
        query = db.query(Favorite).options(
            joinedload(Favorite.user), joinedload(Favorite.book)
        )

        # Apply filters
        if search:
            query = (
                query.join(User)
                .join(Book)
                .filter(
                    or_(
                        User.full_name.ilike(f"%{search}%"),
                        User.username.ilike(f"%{search}%"),
                        Book.title.ilike(f"%{search}%"),
                        Book.description.ilike(f"%{search}%"),
                    )
                )
            )

        if user_id is not None:
            query = query.filter(Favorite.user_id == user_id)

        if book_id is not None:
            query = query.filter(Favorite.book_id == book_id)

        if created_from:
            query = query.filter(Favorite.created_at >= created_from)

        if created_to:
            query = query.filter(Favorite.created_at <= created_to)

        return query.order_by(Favorite.id.desc()).offset(skip).limit(limit).all()

    def count_with_filters(
        self,
        db: Session,
        *,
        search: Optional[str] = None,
        user_id: Optional[int] = None,
        book_id: Optional[int] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
    ) -> int:
        """Count favorites with filters (Admin only)"""
        query = db.query(Favorite)

        # Apply filters
        if search:
            query = (
                query.join(User)
                .join(Book)
                .filter(
                    or_(
                        User.full_name.ilike(f"%{search}%"),
                        User.username.ilike(f"%{search}%"),
                        Book.title.ilike(f"%{search}%"),
                        Book.description.ilike(f"%{search}%"),
                    )
                )
            )

        if user_id is not None:
            query = query.filter(Favorite.user_id == user_id)

        if book_id is not None:
            query = query.filter(Favorite.book_id == book_id)

        if created_from:
            query = query.filter(Favorite.created_at >= created_from)

        if created_to:
            query = query.filter(Favorite.created_at <= created_to)

        return query.count()


crud_favorite = CRUDFavorite(Favorite)
