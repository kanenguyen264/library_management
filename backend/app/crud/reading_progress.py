import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.crud.base import CRUDBase
from app.models.reading_progress import ReadingProgress
from app.schemas.reading_progress import ReadingProgressCreate, ReadingProgressUpdate

logger = logging.getLogger(__name__)


class CRUDReadingProgress(
    CRUDBase[ReadingProgress, ReadingProgressCreate, ReadingProgressUpdate]
):
    def get_by_user_and_book(
        self, db: Session, *, user_id: int, book_id: int
    ) -> Optional[ReadingProgress]:
        return (
            db.query(ReadingProgress)
            .filter(
                ReadingProgress.user_id == user_id, ReadingProgress.book_id == book_id
            )
            .first()
        )

    def get_by_user(
        self, db: Session, *, user_id: int, skip: int = 0, limit: int = 10000
    ) -> List[ReadingProgress]:
        return (
            db.query(ReadingProgress)
            .options(joinedload(ReadingProgress.book))
            .filter(ReadingProgress.user_id == user_id)
            .order_by(ReadingProgress.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_by_user(self, db: Session, *, user_id: int) -> int:
        """Get total count of reading progress for a user."""
        return (
            db.query(ReadingProgress).filter(ReadingProgress.user_id == user_id).count()
        )

    def get_multi_with_details(
        self, db: Session, *, skip: int = 0, limit: int = 10000
    ) -> List[ReadingProgress]:
        """Get reading progress with user and book details (Admin only)."""
        return (
            db.query(ReadingProgress)
            .options(joinedload(ReadingProgress.user), joinedload(ReadingProgress.book))
            .order_by(ReadingProgress.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_completed_by_user(
        self, db: Session, *, user_id: int, skip: int = 0, limit: int = 10000
    ) -> List[ReadingProgress]:
        return (
            db.query(ReadingProgress)
            .options(joinedload(ReadingProgress.book))
            .filter(
                ReadingProgress.user_id == user_id, ReadingProgress.is_completed == True
            )
            .order_by(ReadingProgress.completed_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_completed_by_user(self, db: Session, *, user_id: int) -> int:
        """Get total count of completed reading progress for a user."""
        return (
            db.query(ReadingProgress)
            .filter(
                ReadingProgress.user_id == user_id, ReadingProgress.is_completed == True
            )
            .count()
        )

    def get_currently_reading(
        self, db: Session, *, user_id: int, skip: int = 0, limit: int = 10000
    ) -> List[ReadingProgress]:
        return (
            db.query(ReadingProgress)
            .options(joinedload(ReadingProgress.book))
            .filter(
                ReadingProgress.user_id == user_id, ReadingProgress.status == "reading"
            )
            .order_by(ReadingProgress.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_currently_reading(self, db: Session, *, user_id: int) -> int:
        """Get total count of currently reading books for a user."""
        return (
            db.query(ReadingProgress)
            .filter(
                ReadingProgress.user_id == user_id, ReadingProgress.status == "reading"
            )
            .count()
        )

    def update_progress(
        self,
        db: Session,
        *,
        db_obj: ReadingProgress,
        current_page: int,
        total_pages: int = None,
    ) -> ReadingProgress:
        """Update reading progress with calculated fields."""
        import datetime

        # Update current page
        db_obj.current_page = current_page

        # Update total pages if provided
        if total_pages is not None:
            db_obj.total_pages = total_pages

        # Calculate progress percentage
        if db_obj.total_pages and db_obj.total_pages > 0:
            db_obj.progress_percentage = (current_page / db_obj.total_pages) * 100

        # Update status and timestamps
        db_obj.last_read_at = datetime.datetime.utcnow()

        if db_obj.status == "not_started":
            db_obj.status = "reading"
            db_obj.started_at = datetime.datetime.utcnow()

        # Check if completed
        if db_obj.total_pages and current_page >= db_obj.total_pages:
            db_obj.status = "completed"
            db_obj.is_completed = True
            db_obj.completed_at = datetime.datetime.utcnow()
            db_obj.progress_percentage = 100.0

        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_user_stats(self, db: Session, *, user_id: int) -> Dict[str, Any]:
        """Get reading statistics for a user."""
        total_books = (
            db.query(ReadingProgress).filter(ReadingProgress.user_id == user_id).count()
        )

        completed_books = (
            db.query(ReadingProgress)
            .filter(
                ReadingProgress.user_id == user_id, ReadingProgress.is_completed == True
            )
            .count()
        )

        currently_reading = (
            db.query(ReadingProgress)
            .filter(
                ReadingProgress.user_id == user_id, ReadingProgress.status == "reading"
            )
            .count()
        )

        total_reading_time = (
            db.query(func.sum(ReadingProgress.reading_time_minutes))
            .filter(ReadingProgress.user_id == user_id)
            .scalar()
            or 0
        )

        return {
            "total_books": total_books,
            "completed_books": completed_books,
            "currently_reading": currently_reading,
            "total_reading_time_minutes": total_reading_time,
        }

    def get_multi_with_filters(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 10000,
        search: Optional[str] = None,
        user_id: Optional[int] = None,
        book_id: Optional[int] = None,
        status: Optional[str] = None,
        last_read_from: Optional[str] = None,
        last_read_to: Optional[str] = None,
    ) -> List[ReadingProgress]:
        """Get reading progress with advanced filtering for admin."""
        from app.models.book import Book
        from app.models.user import User

        query = db.query(ReadingProgress).options(
            joinedload(ReadingProgress.user), joinedload(ReadingProgress.book)
        )

        # Search filter (search in user name/email or book title)
        if search:
            search_filter = f"%{search}%"
            query = (
                query.join(User)
                .join(Book)
                .filter(
                    User.username.ilike(search_filter)
                    | User.email.ilike(search_filter)
                    | User.full_name.ilike(search_filter)
                    | Book.title.ilike(search_filter)
                )
            )
        else:
            # Still need to join for other filters
            query = query.join(User).join(Book)

        # User filter
        if user_id:
            query = query.filter(ReadingProgress.user_id == user_id)

        # Book filter
        if book_id:
            query = query.filter(ReadingProgress.book_id == book_id)

        # Status filter
        if status and status != "all":
            query = query.filter(ReadingProgress.status == status)

        # Last read date range filters
        if last_read_from:
            try:
                from datetime import datetime

                last_read_from_date = datetime.fromisoformat(
                    last_read_from.replace("Z", "+00:00")
                )
                query = query.filter(
                    ReadingProgress.last_read_at >= last_read_from_date
                )
            except ValueError:
                pass  # Invalid date format, ignore filter

        if last_read_to:
            try:
                from datetime import datetime

                last_read_to_date = datetime.fromisoformat(
                    last_read_to.replace("Z", "+00:00")
                )
                query = query.filter(ReadingProgress.last_read_at <= last_read_to_date)
            except ValueError:
                pass  # Invalid date format, ignore filter

        return query.order_by(ReadingProgress.id.desc()).offset(skip).limit(limit).all()

    def count_with_filters(
        self,
        db: Session,
        *,
        search: Optional[str] = None,
        user_id: Optional[int] = None,
        book_id: Optional[int] = None,
        status: Optional[str] = None,
        last_read_from: Optional[str] = None,
        last_read_to: Optional[str] = None,
    ) -> int:
        """Count reading progress records with filters for admin."""
        from app.models.book import Book
        from app.models.user import User

        query = db.query(ReadingProgress)

        # Search filter
        if search:
            search_filter = f"%{search}%"
            query = (
                query.join(User)
                .join(Book)
                .filter(
                    User.username.ilike(search_filter)
                    | User.email.ilike(search_filter)
                    | User.full_name.ilike(search_filter)
                    | Book.title.ilike(search_filter)
                )
            )
        else:
            query = query.join(User).join(Book)

        # User filter
        if user_id:
            query = query.filter(ReadingProgress.user_id == user_id)

        # Book filter
        if book_id:
            query = query.filter(ReadingProgress.book_id == book_id)

        # Status filter
        if status and status != "all":
            query = query.filter(ReadingProgress.status == status)

        # Last read date range filters
        if last_read_from:
            try:
                from datetime import datetime

                last_read_from_date = datetime.fromisoformat(
                    last_read_from.replace("Z", "+00:00")
                )
                query = query.filter(
                    ReadingProgress.last_read_at >= last_read_from_date
                )
            except ValueError:
                pass

        if last_read_to:
            try:
                from datetime import datetime

                last_read_to_date = datetime.fromisoformat(
                    last_read_to.replace("Z", "+00:00")
                )
                query = query.filter(ReadingProgress.last_read_at <= last_read_to_date)
            except ValueError:
                pass

        return query.count()


crud_reading_progress = CRUDReadingProgress(ReadingProgress)
