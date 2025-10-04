import logging
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from app.core.supabase_client import supabase_client
from app.crud.base import CRUDBase
from app.models.book import Book
from app.schemas.book import BookCreate, BookUpdate

logger = logging.getLogger(__name__)


class CRUDBook(CRUDBase[Book, BookCreate, BookUpdate]):
    def create(self, db: Session, *, obj_in: BookCreate) -> Book:
        """Create book with proper handling of empty strings to NULL."""
        obj_in_data = obj_in.model_dump()

        # Convert empty strings to None for optional fields
        optional_string_fields = [
            "isbn",
            "description",
            "language",
            "cover_url",
            "pdf_url",
            "epub_url",
        ]
        for field in optional_string_fields:
            if field in obj_in_data and obj_in_data[field] == "":
                obj_in_data[field] = None

        # Convert 0 to None for optional numeric fields
        optional_numeric_fields = ["pages", "price"]
        for field in optional_numeric_fields:
            if field in obj_in_data and obj_in_data[field] == 0:
                obj_in_data[field] = None

        db_obj = self.model(**obj_in_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_with_details(self, db: Session, id: int) -> Optional[Book]:
        return (
            db.query(Book)
            .options(joinedload(Book.author), joinedload(Book.category))
            .filter(Book.id == id)
            .first()
        )

    def get_multi_with_details(
        self, db: Session, *, skip: int = 0, limit: int = 10000
    ) -> List[Book]:
        return (
            db.query(Book)
            .options(joinedload(Book.author), joinedload(Book.category))
            .order_by(Book.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_title(self, db: Session, *, title: str) -> Optional[Book]:
        return db.query(Book).filter(Book.title == title).first()

    def get_by_isbn(self, db: Session, *, isbn: str) -> Optional[Book]:
        return db.query(Book).filter(Book.isbn == isbn).first()

    def get_by_author(
        self, db: Session, *, author_id: int, skip: int = 0, limit: int = 10000
    ) -> List[Book]:
        return (
            db.query(Book)
            .filter(Book.author_id == author_id)
            .order_by(Book.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_category(
        self, db: Session, *, category_id: int, skip: int = 0, limit: int = 10000
    ) -> List[Book]:
        return (
            db.query(Book)
            .filter(Book.category_id == category_id)
            .order_by(Book.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_free_books(
        self, db: Session, *, skip: int = 0, limit: int = 10000
    ) -> List[Book]:
        return (
            db.query(Book)
            .filter(and_(Book.is_free == True, Book.is_active == True))
            .order_by(Book.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def search_books(
        self, db: Session, *, query: str, skip: int = 0, limit: int = 10000
    ) -> List[Book]:
        return (
            db.query(Book)
            .options(joinedload(Book.author), joinedload(Book.category))
            .filter(
                and_(
                    Book.is_active == True,
                    func.lower(Book.title).contains(func.lower(query))
                    | func.lower(Book.description).contains(func.lower(query)),
                )
            )
            .order_by(Book.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_active_books(
        self, db: Session, *, skip: int = 0, limit: int = 10000
    ) -> List[Book]:
        return (
            db.query(Book)
            .filter(Book.is_active == True)
            .order_by(Book.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def _cleanup_book_files(self, book: Book) -> None:
        """
        Delete all files associated with a book from Supabase storage.
        """
        try:
            files_to_delete = []

            # Collect all file URLs that need to be deleted
            if book.cover_url:
                files_to_delete.append(("Cover", book.cover_url))
            if book.pdf_url:
                files_to_delete.append(("PDF", book.pdf_url))
            if book.epub_url:
                files_to_delete.append(("EPUB", book.epub_url))

            if not files_to_delete:
                logger.info(f"No files to delete for book: {book.title}")
                return

            logger.info(f"Deleting {len(files_to_delete)} files for book: {book.title}")

            # Delete each file
            for file_type, file_url in files_to_delete:
                try:
                    success = supabase_client.delete_file(file_url)
                    if success:
                        logger.info(
                            f"{file_type} file deleted successfully: {file_url}"
                        )
                    else:
                        logger.warning(f"Failed to delete {file_type} file: {file_url}")
                except Exception as file_error:
                    logger.error(
                        f"Error deleting {file_type} file {file_url}: {str(file_error)}"
                    )

        except Exception as e:
            logger.error(f"Error cleaning up book files for {book.title}: {str(e)}")

    def _cleanup_old_files_on_update(
        self, old_book: Book, update_data: Dict[str, Any]
    ) -> None:
        """
        Delete old files when they are being replaced with new ones or removed.
        """
        try:
            logger.info(f"Checking file changes for book: {old_book.title}")

            # Check cover_url update
            if "cover_url" in update_data:
                new_cover_url = update_data["cover_url"] or ""  # Handle None
                old_cover_url = old_book.cover_url or ""  # Handle None

                # If URLs are different AND old URL exists, delete old file
                if new_cover_url != old_cover_url and old_cover_url:
                    logger.info(
                        f"Cover URL changed, deleting old cover: {old_cover_url}"
                    )
                    try:
                        success = supabase_client.delete_file(old_cover_url)
                        if success:
                            logger.info(
                                f"Successfully deleted old cover: {old_cover_url}"
                            )
                        else:
                            logger.warning(
                                f"Failed to delete old cover: {old_cover_url}"
                            )
                    except Exception as e:
                        logger.error(
                            f"Error deleting old cover {old_cover_url}: {str(e)}"
                        )

            # Check pdf_url update
            if "pdf_url" in update_data:
                new_pdf_url = update_data["pdf_url"] or ""  # Handle None
                old_pdf_url = old_book.pdf_url or ""  # Handle None

                # If URLs are different AND old URL exists, delete old file
                if new_pdf_url != old_pdf_url and old_pdf_url:
                    logger.info(f"PDF URL changed, deleting old PDF: {old_pdf_url}")
                    try:
                        success = supabase_client.delete_file(old_pdf_url)
                        if success:
                            logger.info(f"Successfully deleted old PDF: {old_pdf_url}")
                        else:
                            logger.warning(f"Failed to delete old PDF: {old_pdf_url}")
                    except Exception as e:
                        logger.error(f"Error deleting old PDF {old_pdf_url}: {str(e)}")

            # Check epub_url update
            if "epub_url" in update_data:
                new_epub_url = update_data["epub_url"] or ""  # Handle None
                old_epub_url = old_book.epub_url or ""  # Handle None

                # If URLs are different AND old URL exists, delete old file
                if new_epub_url != old_epub_url and old_epub_url:
                    logger.info(f"EPUB URL changed, deleting old EPUB: {old_epub_url}")
                    try:
                        success = supabase_client.delete_file(old_epub_url)
                        if success:
                            logger.info(
                                f"Successfully deleted old EPUB: {old_epub_url}"
                            )
                        else:
                            logger.warning(f"Failed to delete old EPUB: {old_epub_url}")
                    except Exception as e:
                        logger.error(
                            f"Error deleting old EPUB {old_epub_url}: {str(e)}"
                        )

        except Exception as e:
            logger.error(f"Error cleaning up old files for {old_book.title}: {str(e)}")

    def remove(self, db: Session, *, id: int, force: bool = False) -> Book:
        """
        Delete a book and cleanup all associated files.

        Args:
            id: Book ID to delete
            force: If False, will check for chapters and raise ValueError if found.
                  If True, will delete all related data automatically.
        """
        from app.models.chapter import Chapter
        from app.models.reading_progress import ReadingProgress

        # Get the book first to access file URLs
        book = self.get(db, id=id)
        if not book:
            logger.warning(f"Book with ID {id} not found for deletion")
            return None

        logger.info(f"Deleting book: {book.title} (ID: {id})")

        try:
            # Check constraints if not forcing
            chapter_count = db.query(Chapter).filter(Chapter.book_id == id).count()
            progress_count = (
                db.query(ReadingProgress).filter(ReadingProgress.book_id == id).count()
            )

            if not force and chapter_count > 0:
                logger.warning(
                    f"Cannot delete book {book.title}: {chapter_count} chapters are associated with this book"
                )
                raise ValueError(
                    f"Cannot delete book. There are {chapter_count} chapters associated with this book. Please delete the chapters first or use force delete."
                )

            # Cleanup all files before deleting the record
            self._cleanup_book_files(book)

            # Manually delete related records first to avoid foreign key constraint issues
            if progress_count > 0:
                logger.info(f"Deleting {progress_count} reading progress records")
                db.query(ReadingProgress).filter(ReadingProgress.book_id == id).delete()

            if chapter_count > 0:
                logger.info(f"Deleting {chapter_count} chapter records")
                db.query(Chapter).filter(Chapter.book_id == id).delete()

            # Delete the book record
            db.delete(book)
            db.commit()

            logger.info(f"Book deleted successfully: {book.title}")
            return book
        except Exception as e:
            # Rollback the transaction if deletion fails
            db.rollback()
            logger.error(f"Error deleting book {id}: {str(e)}")
            raise e

    def update(
        self, db: Session, *, db_obj: Book, obj_in: Union[BookUpdate, Dict[str, Any]]
    ) -> Book:
        """Update book with proper handling of empty strings to NULL."""
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)

        # Convert empty strings to None for optional fields
        optional_string_fields = [
            "isbn",
            "description",
            "language",
            "cover_url",
            "pdf_url",
            "epub_url",
        ]
        for field in optional_string_fields:
            if field in update_data and update_data[field] == "":
                update_data[field] = None

        # Convert 0 to None for optional numeric fields (but only if explicitly set)
        optional_numeric_fields = ["pages", "price"]
        for field in optional_numeric_fields:
            if field in update_data and update_data[field] == 0:
                update_data[field] = None

        logger.info(f"Updating book: {db_obj.title} (ID: {db_obj.id})")

        # Cleanup old files that are being replaced
        self._cleanup_old_files_on_update(db_obj, update_data)

        # Perform the update
        try:
            updated_book = super().update(db, db_obj=db_obj, obj_in=update_data)
            logger.info(f"Book updated successfully: {updated_book.title}")
            return updated_book
        except Exception as e:
            logger.error(f"Error updating book {db_obj.id}: {str(e)}")
            raise e

    # PUBLIC METHODS FOR USER SITE
    def get_active_books_with_details(
        self, db: Session, *, skip: int = 0, limit: int = 100
    ) -> List[Book]:
        """Get active books with author and category details for public access."""
        return (
            db.query(Book)
            .options(joinedload(Book.author), joinedload(Book.category))
            .filter(Book.is_active == True)
            .order_by(Book.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_public_free_books(
        self, db: Session, *, skip: int = 0, limit: int = 100
    ) -> List[Book]:
        """Get free and active books with details for public access."""
        return (
            db.query(Book)
            .options(joinedload(Book.author), joinedload(Book.category))
            .filter(Book.is_free == True, Book.is_active == True)
            .order_by(Book.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_featured_books(self, db: Session, *, limit: int = 10) -> List[Book]:
        """Get featured books (most recent active books) for homepage."""
        return (
            db.query(Book)
            .options(joinedload(Book.author), joinedload(Book.category))
            .filter(Book.is_active == True)
            .order_by(Book.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_public_books_by_category(
        self, db: Session, *, category_id: int, skip: int = 0, limit: int = 100
    ) -> List[Book]:
        """Get active books by category with details for public access."""
        return (
            db.query(Book)
            .options(joinedload(Book.author), joinedload(Book.category))
            .filter(Book.category_id == category_id, Book.is_active == True)
            .order_by(Book.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_public_books_by_author(
        self, db: Session, *, author_id: int, skip: int = 0, limit: int = 100
    ) -> List[Book]:
        """Get active books by author with details for public access."""
        return (
            db.query(Book)
            .options(joinedload(Book.author), joinedload(Book.category))
            .filter(Book.author_id == author_id, Book.is_active == True)
            .order_by(Book.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def search_public_books(
        self, db: Session, *, query: str, skip: int = 0, limit: int = 100
    ) -> List[Book]:
        """Search active books for public access."""
        return (
            db.query(Book)
            .options(joinedload(Book.author), joinedload(Book.category))
            .filter(
                Book.is_active == True,
                (Book.title.ilike(f"%{query}%") | Book.description.ilike(f"%{query}%")),
            )
            .order_by(Book.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_public_book_with_details(self, db: Session, *, id: int) -> Optional[Book]:
        """Get active book with details for public access."""
        return (
            db.query(Book)
            .options(joinedload(Book.author), joinedload(Book.category))
            .filter(Book.id == id, Book.is_active == True)
            .first()
        )

    def count_active_books(self, db: Session) -> int:
        """Get total count of active books."""
        return db.query(Book).filter(Book.is_active == True).count()

    def count_by_author(self, db: Session, *, author_id: int) -> int:
        """Get total count of books by author."""
        return db.query(Book).filter(Book.author_id == author_id).count()

    def count_by_category(self, db: Session, *, category_id: int) -> int:
        """Get total count of books by category."""
        return db.query(Book).filter(Book.category_id == category_id).count()

    def count_free_books(self, db: Session) -> int:
        """Get total count of free books."""
        return (
            db.query(Book)
            .filter(and_(Book.is_free == True, Book.is_active == True))
            .count()
        )

    def count_search_books(self, db: Session, *, query: str) -> int:
        """Get total count of books matching search query."""
        return (
            db.query(Book)
            .filter(
                and_(
                    Book.is_active == True,
                    func.lower(Book.title).contains(func.lower(query))
                    | func.lower(Book.description).contains(func.lower(query)),
                )
            )
            .count()
        )

    def get_public_book(self, db: Session, *, id: int) -> Optional[Book]:
        """Get active book by ID for public access."""
        return (
            db.query(Book)
            .options(joinedload(Book.author), joinedload(Book.category))
            .filter(Book.id == id, Book.is_active == True)
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
        author_id: Optional[int] = None,
        category_id: Optional[int] = None,
        is_active: Optional[bool] = None,
        is_free: Optional[bool] = None,
        publication_date_from: Optional[str] = None,
        publication_date_to: Optional[str] = None,
    ) -> List[Book]:
        """Get books with comprehensive filtering and search."""
        from datetime import datetime

        query = db.query(Book).options(
            joinedload(Book.author), joinedload(Book.category)
        )

        # Apply search filter
        if search:
            search_filter = Book.title.ilike(f"%{search}%") | Book.description.ilike(
                f"%{search}%"
            )
            query = query.filter(search_filter)

        # Apply basic filters
        if author_id is not None:
            query = query.filter(Book.author_id == author_id)

        if category_id is not None:
            query = query.filter(Book.category_id == category_id)

        if is_active is not None:
            query = query.filter(Book.is_active == is_active)

        if is_free is not None:
            query = query.filter(Book.is_free == is_free)

        # Apply date range filters
        if publication_date_from:
            try:
                date_from = datetime.strptime(publication_date_from, "%Y-%m-%d").date()
                query = query.filter(Book.publication_date >= date_from)
            except ValueError:
                logger.warning(
                    f"Invalid publication_date_from format: {publication_date_from}"
                )

        if publication_date_to:
            try:
                date_to = datetime.strptime(publication_date_to, "%Y-%m-%d").date()
                query = query.filter(Book.publication_date <= date_to)
            except ValueError:
                logger.warning(
                    f"Invalid publication_date_to format: {publication_date_to}"
                )

        return query.order_by(Book.id.desc()).offset(skip).limit(limit).all()

    def count_with_filters(
        self,
        db: Session,
        *,
        search: Optional[str] = None,
        author_id: Optional[int] = None,
        category_id: Optional[int] = None,
        is_active: Optional[bool] = None,
        is_free: Optional[bool] = None,
        publication_date_from: Optional[str] = None,
        publication_date_to: Optional[str] = None,
    ) -> int:
        """Count books with comprehensive filtering."""
        from datetime import datetime

        query = db.query(Book)

        # Apply search filter
        if search:
            search_filter = Book.title.ilike(f"%{search}%") | Book.description.ilike(
                f"%{search}%"
            )
            query = query.filter(search_filter)

        # Apply basic filters
        if author_id is not None:
            query = query.filter(Book.author_id == author_id)

        if category_id is not None:
            query = query.filter(Book.category_id == category_id)

        if is_active is not None:
            query = query.filter(Book.is_active == is_active)

        if is_free is not None:
            query = query.filter(Book.is_free == is_free)

        # Apply date range filters
        if publication_date_from:
            try:
                date_from = datetime.strptime(publication_date_from, "%Y-%m-%d").date()
                query = query.filter(Book.publication_date >= date_from)
            except ValueError:
                logger.warning(
                    f"Invalid publication_date_from format: {publication_date_from}"
                )

        if publication_date_to:
            try:
                date_to = datetime.strptime(publication_date_to, "%Y-%m-%d").date()
                query = query.filter(Book.publication_date <= date_to)
            except ValueError:
                logger.warning(
                    f"Invalid publication_date_to format: {publication_date_to}"
                )

        return query.count()


crud_book = CRUDBook(Book)
