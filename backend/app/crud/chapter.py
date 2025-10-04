import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from app.crud.base import CRUDBase
from app.models.chapter import Chapter
from app.schemas.chapter import ChapterCreate, ChapterUpdate

logger = logging.getLogger(__name__)


class CRUDChapter(CRUDBase[Chapter, ChapterCreate, ChapterUpdate]):
    def get_with_details(self, db: Session, *, id: int) -> Optional[Chapter]:
        """Get chapter with book details."""
        return (
            db.query(Chapter)
            .options(joinedload(Chapter.book))
            .filter(Chapter.id == id)
            .first()
        )

    def get_multi_with_details(
        self, db: Session, *, skip: int = 0, limit: int = 10000
    ) -> List[Chapter]:
        """Get multiple chapters with book details."""
        return (
            db.query(Chapter)
            .options(joinedload(Chapter.book))
            .order_by(Chapter.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_multi_with_filters(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 10000,
        search: Optional[str] = None,
        is_published: Optional[bool] = None,
        is_active: Optional[bool] = None,
        book_id: Optional[int] = None,
        created_from: Optional[str] = None,
        created_to: Optional[str] = None,
    ) -> List[Chapter]:
        """Get chapters with comprehensive filtering."""
        query = db.query(Chapter).options(joinedload(Chapter.book))

        filters = []

        # Search filter
        if search:
            filters.append(
                Chapter.title.ilike(f"%{search}%")
                | Chapter.content.ilike(f"%{search}%")
            )

        # Status filters
        if is_published is not None:
            filters.append(Chapter.is_published == is_published)

        if is_active is not None:
            filters.append(Chapter.is_active == is_active)

        # Book filter
        if book_id is not None:
            filters.append(Chapter.book_id == book_id)

        # Date filters
        if created_from:
            try:
                from_date = datetime.strptime(created_from, "%Y-%m-%d")
                filters.append(func.date(Chapter.created_at) >= from_date.date())
            except ValueError:
                pass  # Invalid date format, skip filter

        if created_to:
            try:
                to_date = datetime.strptime(created_to, "%Y-%m-%d")
                filters.append(func.date(Chapter.created_at) <= to_date.date())
            except ValueError:
                pass  # Invalid date format, skip filter

        if filters:
            query = query.filter(and_(*filters))

        return query.order_by(Chapter.id.desc()).offset(skip).limit(limit).all()

    def count_with_filters(
        self,
        db: Session,
        *,
        search: Optional[str] = None,
        is_published: Optional[bool] = None,
        is_active: Optional[bool] = None,
        book_id: Optional[int] = None,
        created_from: Optional[str] = None,
        created_to: Optional[str] = None,
    ) -> int:
        """Get count of chapters with comprehensive filtering."""
        query = db.query(Chapter)

        filters = []

        # Search filter
        if search:
            filters.append(
                Chapter.title.ilike(f"%{search}%")
                | Chapter.content.ilike(f"%{search}%")
            )

        # Status filters
        if is_published is not None:
            filters.append(Chapter.is_published == is_published)

        if is_active is not None:
            filters.append(Chapter.is_active == is_active)

        # Book filter
        if book_id is not None:
            filters.append(Chapter.book_id == book_id)

        # Date filters
        if created_from:
            try:
                from_date = datetime.strptime(created_from, "%Y-%m-%d")
                filters.append(func.date(Chapter.created_at) >= from_date.date())
            except ValueError:
                pass  # Invalid date format, skip filter

        if created_to:
            try:
                to_date = datetime.strptime(created_to, "%Y-%m-%d")
                filters.append(func.date(Chapter.created_at) <= to_date.date())
            except ValueError:
                pass  # Invalid date format, skip filter

        if filters:
            query = query.filter(and_(*filters))

        return query.count()

    def get_by_book(
        self, db: Session, *, book_id: int, skip: int = 0, limit: int = 10000
    ) -> List[Chapter]:
        """Get chapters by book ID ordered by chapter number."""
        return (
            db.query(Chapter)
            .options(joinedload(Chapter.book))
            .filter(Chapter.book_id == book_id)
            .order_by(Chapter.chapter_number)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_by_book(self, db: Session, *, book_id: int) -> int:
        """Get total count of chapters for a book."""
        return db.query(Chapter).filter(Chapter.book_id == book_id).count()

    def get_published_chapters(
        self, db: Session, *, book_id: int, skip: int = 0, limit: int = 10000
    ) -> List[Chapter]:
        """Get published chapters for a book."""
        return (
            db.query(Chapter)
            .options(joinedload(Chapter.book))
            .filter(Chapter.book_id == book_id, Chapter.is_published == True)
            .order_by(Chapter.chapter_number)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_published_chapters(self, db: Session, *, book_id: int) -> int:
        """Get total count of published chapters for a book."""
        return (
            db.query(Chapter)
            .filter(Chapter.book_id == book_id, Chapter.is_published == True)
            .count()
        )

    def get_by_book_and_chapter_number(
        self, db: Session, *, book_id: int, chapter_number: int
    ) -> Optional[Chapter]:
        """Get chapter by book ID and chapter number."""
        return (
            db.query(Chapter)
            .filter(
                Chapter.book_id == book_id, Chapter.chapter_number == chapter_number
            )
            .first()
        )

    def get_active_chapters(
        self, db: Session, *, skip: int = 0, limit: int = 10000
    ) -> List[Chapter]:
        """Get active chapters."""
        return (
            db.query(Chapter)
            .filter(Chapter.is_active == True)
            .order_by(Chapter.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_active_chapters(self, db: Session) -> int:
        """Get total count of active chapters."""
        return db.query(Chapter).filter(Chapter.is_active == True).count()

    def search_chapters(
        self, db: Session, *, query: str, skip: int = 0, limit: int = 10000
    ) -> List[Chapter]:
        """Search chapters by title or content."""
        return (
            db.query(Chapter)
            .options(joinedload(Chapter.book))
            .filter(
                Chapter.title.ilike(f"%{query}%") | Chapter.content.ilike(f"%{query}%")
            )
            .order_by(Chapter.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_search_chapters(self, db: Session, *, query: str) -> int:
        """Get total count of chapters matching search query."""
        return (
            db.query(Chapter)
            .filter(
                Chapter.title.ilike(f"%{query}%") | Chapter.content.ilike(f"%{query}%")
            )
            .count()
        )

    def remove(self, db: Session, *, id: int) -> Chapter:
        """
        Delete a chapter with constraint validation.
        """
        from app.models.reading_progress import ReadingProgress

        # Get the chapter first
        chapter = self.get(db, id=id)
        if not chapter:
            return None

        # Check if there are reading progress records for this chapter
        progress_count = (
            db.query(ReadingProgress)
            .filter(ReadingProgress.book_id == chapter.book_id)
            .count()
        )

        if progress_count > 0:
            # Instead of hard deletion, mark as inactive
            chapter.is_active = False
            db.commit()
            db.refresh(chapter)
            return chapter

        # If no dependencies, proceed with hard deletion
        db.delete(chapter)
        db.commit()
        return chapter

    # PUBLIC METHODS FOR USER SITE
    def get_public_chapters_by_book(
        self, db: Session, *, book_id: int, skip: int = 0, limit: int = 100
    ) -> List[Chapter]:
        """Get published chapters for public access."""
        return (
            db.query(Chapter)
            .options(joinedload(Chapter.book))
            .filter(
                Chapter.book_id == book_id,
                Chapter.is_published == True,
                Chapter.is_active == True,
            )
            .order_by(Chapter.chapter_number)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_public_chapters_by_book(self, db: Session, *, book_id: int) -> int:
        """Get total count of public chapters for a book."""
        return (
            db.query(Chapter)
            .filter(
                Chapter.book_id == book_id,
                Chapter.is_published == True,
                Chapter.is_active == True,
            )
            .count()
        )

    def get_public_chapter(self, db: Session, *, id: int) -> Optional[Chapter]:
        """Get published chapter by ID for public access."""
        return (
            db.query(Chapter)
            .options(joinedload(Chapter.book))
            .filter(
                Chapter.id == id,
                Chapter.is_published == True,
                Chapter.is_active == True,
            )
            .first()
        )

    def get_all_published_chapters(
        self, db: Session, *, skip: int = 0, limit: int = 10000
    ) -> List[Chapter]:
        """Get all published chapters from all books."""
        return (
            db.query(Chapter)
            .options(joinedload(Chapter.book))
            .filter(Chapter.is_published == True)
            .order_by(Chapter.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_all_published_chapters(self, db: Session) -> int:
        """Get total count of all published chapters."""
        return db.query(Chapter).filter(Chapter.is_published == True).count()


crud_chapter = CRUDChapter(Chapter)
