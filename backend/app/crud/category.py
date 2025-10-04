import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryUpdate

logger = logging.getLogger(__name__)


class CRUDCategory(CRUDBase[Category, CategoryCreate, CategoryUpdate]):
    def get_by_name(self, db: Session, *, name: str) -> Optional[Category]:
        return db.query(Category).filter(Category.name == name).first()

    def get_by_slug(self, db: Session, *, slug: str) -> Optional[Category]:
        return db.query(Category).filter(Category.slug == slug).first()

    def get_active(
        self, db: Session, *, skip: int = 0, limit: int = 10000
    ) -> List[Category]:
        return (
            db.query(Category)
            .filter(Category.is_active == True)
            .order_by(Category.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_active(self, db: Session) -> int:
        """Get total count of active categories."""
        return db.query(Category).filter(Category.is_active == True).count()

    def search_by_name(
        self, db: Session, *, name: str, skip: int = 0, limit: int = 10000
    ) -> List[Category]:
        return (
            db.query(Category)
            .filter(Category.name.ilike(f"%{name}%"))
            .order_by(Category.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_search_by_name(self, db: Session, *, name: str) -> int:
        """Get total count of categories matching search term."""
        return db.query(Category).filter(Category.name.ilike(f"%{name}%")).count()

    def remove(self, db: Session, *, id: int) -> Category:
        """
        Delete a category with constraint validation.
        """
        from app.models.book import Book

        # Get the category first
        category = self.get(db, id=id)
        if not category:
            return None

        # Check if there are any books associated with this category
        books_count = db.query(Book).filter(Book.category_id == id).count()
        if books_count > 0:
            raise ValueError(
                f"Cannot delete category. {books_count} books are still associated with this category."
            )

        # If no books are associated, proceed with deletion
        db.delete(category)
        db.commit()
        return category

    def get_active_categories(
        self, db: Session, *, skip: int = 0, limit: int = 100
    ) -> List[Category]:
        """
        Get active categories for public endpoints.
        """
        return (
            db.query(Category)
            .filter(Category.is_active == True)
            .order_by(Category.name)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_active_category(self, db: Session, *, id: int) -> Optional[Category]:
        """
        Get an active category by ID for public endpoints.
        """
        return (
            db.query(Category)
            .filter(Category.id == id, Category.is_active == True)
            .first()
        )

    # COMPREHENSIVE FILTERING METHODS FOR ADMIN
    def get_multi_with_filters(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 10000,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        created_from: Optional[str] = None,
        created_to: Optional[str] = None,
    ) -> List[Category]:
        """Get categories with comprehensive filtering and search."""
        from datetime import datetime

        query = db.query(Category)

        # Apply search filter
        if search:
            search_filter = Category.name.ilike(
                f"%{search}%"
            ) | Category.description.ilike(f"%{search}%")
            query = query.filter(search_filter)

        # Apply active status filter
        if is_active is not None:
            query = query.filter(Category.is_active == is_active)

        # Apply date range filters
        if created_from:
            try:
                created_from_dt = datetime.strptime(created_from, "%Y-%m-%d")
                query = query.filter(Category.created_at >= created_from_dt)
            except ValueError:
                logger.warning(f"Invalid created_from format: {created_from}")

        if created_to:
            try:
                created_to_dt = datetime.strptime(created_to, "%Y-%m-%d")
                # Add one day and subtract one second to include the entire day
                from datetime import timedelta

                created_to_dt += timedelta(days=1, seconds=-1)
                query = query.filter(Category.created_at <= created_to_dt)
            except ValueError:
                logger.warning(f"Invalid created_to format: {created_to}")

        return query.order_by(Category.id.desc()).offset(skip).limit(limit).all()

    def count_with_filters(
        self,
        db: Session,
        *,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        created_from: Optional[str] = None,
        created_to: Optional[str] = None,
    ) -> int:
        """Count categories with comprehensive filtering."""
        from datetime import datetime

        query = db.query(Category)

        # Apply search filter
        if search:
            search_filter = Category.name.ilike(
                f"%{search}%"
            ) | Category.description.ilike(f"%{search}%")
            query = query.filter(search_filter)

        # Apply active status filter
        if is_active is not None:
            query = query.filter(Category.is_active == is_active)

        # Apply date range filters
        if created_from:
            try:
                created_from_dt = datetime.strptime(created_from, "%Y-%m-%d")
                query = query.filter(Category.created_at >= created_from_dt)
            except ValueError:
                logger.warning(f"Invalid created_from format: {created_from}")

        if created_to:
            try:
                created_to_dt = datetime.strptime(created_to, "%Y-%m-%d")
                # Add one day and subtract one second to include the entire day
                from datetime import timedelta

                created_to_dt += timedelta(days=1, seconds=-1)
                query = query.filter(Category.created_at <= created_to_dt)
            except ValueError:
                logger.warning(f"Invalid created_to format: {created_to}")

        return query.count()


crud_category = CRUDCategory(Category)
