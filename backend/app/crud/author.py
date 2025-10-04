import logging
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.core.supabase_client import supabase_client
from app.crud.base import CRUDBase
from app.models.author import Author
from app.models.book import Book
from app.schemas.author import AuthorCreate, AuthorUpdate

logger = logging.getLogger(__name__)


class CRUDAuthor(CRUDBase[Author, AuthorCreate, AuthorUpdate]):
    def create(self, db: Session, *, obj_in: AuthorCreate) -> Author:
        """Create author with proper handling of empty strings to NULL."""
        obj_in_data = obj_in.model_dump()

        # Convert empty strings to None for optional fields
        optional_string_fields = ["bio", "nationality", "website", "image_url"]
        for field in optional_string_fields:
            if field in obj_in_data and obj_in_data[field] == "":
                obj_in_data[field] = None

        # Convert empty date strings to None
        optional_date_fields = ["birth_date", "death_date"]
        for field in optional_date_fields:
            if field in obj_in_data and obj_in_data[field] == "":
                obj_in_data[field] = None

        db_obj = self.model(**obj_in_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_by_name(self, db: Session, *, name: str) -> Optional[Author]:
        return db.query(Author).filter(Author.name == name).first()

    def search_by_name(
        self, db: Session, *, name: str, skip: int = 0, limit: int = 10000
    ) -> List[Author]:
        return (
            db.query(Author)
            .filter(Author.name.ilike(f"%{name}%"))
            .order_by(Author.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_search_by_name(self, db: Session, *, name: str) -> int:
        """Get total count of authors matching search term."""
        return db.query(Author).filter(Author.name.ilike(f"%{name}%")).count()

    def get_by_nationality(
        self, db: Session, *, nationality: str, skip: int = 0, limit: int = 10000
    ) -> List[Author]:
        return (
            db.query(Author)
            .filter(Author.nationality == nationality)
            .order_by(Author.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_by_nationality(self, db: Session, *, nationality: str) -> int:
        """Get total count of authors by nationality."""
        return db.query(Author).filter(Author.nationality == nationality).count()

    def get_authors_with_book_count(
        self, db: Session, *, skip: int = 0, limit: int = 10000
    ) -> List[dict]:
        """
        Get authors with their book count
        """
        from app.models.book import Book

        return (
            db.query(
                Author.id,
                Author.name,
                Author.bio,
                Author.nationality,
                Author.website,
                Author.image_url,
                Author.created_at,
                Author.updated_at,
                func.count(Book.id).label("book_count"),
            )
            .outerjoin(Book)
            .group_by(Author.id)
            .order_by(Author.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def _cleanup_author_files(self, author: Author) -> None:
        """
        Delete all files associated with an author from Supabase storage.
        """
        try:
            if not author.image_url:
                logger.info(f"No image to delete for author: {author.name}")
                return

            logger.info(f"Deleting image for author: {author.name}")

            try:
                success = supabase_client.delete_file(author.image_url)
                if success:
                    logger.info(
                        f"Author image deleted successfully: {author.image_url}"
                    )
                else:
                    logger.warning(f"Failed to delete author image: {author.image_url}")
            except Exception as file_error:
                logger.error(
                    f"Error deleting author image {author.image_url}: {str(file_error)}"
                )

        except Exception as e:
            logger.error(f"Error cleaning up author files for {author.name}: {str(e)}")

    def _cleanup_old_files_on_update(
        self, old_author: Author, update_data: Dict[str, Any]
    ) -> None:
        """
        Delete old image when it is being replaced with a new one or removed.
        """
        try:
            logger.info(f"Checking file changes for author: {old_author.name}")

            # Check image_url update
            if "image_url" in update_data:
                new_image_url = update_data["image_url"] or ""  # Handle None
                old_image_url = old_author.image_url or ""  # Handle None

                # If URLs are different AND old URL exists, delete old file
                if new_image_url != old_image_url and old_image_url:
                    logger.info(
                        f"Image URL changed, deleting old image: {old_image_url}"
                    )
                    try:
                        success = supabase_client.delete_file(old_image_url)
                        if success:
                            logger.info(
                                f"Successfully deleted old author image: {old_image_url}"
                            )
                        else:
                            logger.warning(
                                f"Failed to delete old author image: {old_image_url}"
                            )
                    except Exception as e:
                        logger.error(
                            f"Error deleting old author image {old_image_url}: {str(e)}"
                        )

        except Exception as e:
            logger.error(f"Error cleaning up old files for {old_author.name}: {str(e)}")

    def remove(self, db: Session, *, id: int) -> Author:
        """
        Delete an author with constraint validation.
        """
        from app.models.book import Book

        # Get the author first
        author = self.get(db, id=id)
        if not author:
            return None

        # Check if there are any books associated with this author
        books_count = db.query(Book).filter(Book.author_id == id).count()
        if books_count > 0:
            raise ValueError(
                f"Cannot delete author. {books_count} books are still associated with this author."
            )

        # If no books are associated, proceed with deletion
        db.delete(author)
        db.commit()
        return author

    def update(
        self,
        db: Session,
        *,
        db_obj: Author,
        obj_in: Union[AuthorUpdate, Dict[str, Any]],
    ) -> Author:
        """Update author with proper handling of empty strings to NULL."""
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)

        # Convert empty strings to None for optional fields
        optional_string_fields = ["bio", "nationality", "website", "image_url"]
        for field in optional_string_fields:
            if field in update_data and update_data[field] == "":
                update_data[field] = None

        # Convert empty date strings to None
        optional_date_fields = ["birth_date", "death_date"]
        for field in optional_date_fields:
            if field in update_data and update_data[field] == "":
                update_data[field] = None

        logger.info(f"Updating author: {db_obj.name} (ID: {db_obj.id})")

        # Cleanup old files that are being replaced
        self._cleanup_old_files_on_update(db_obj, update_data)

        # Perform the update
        try:
            updated_author = super().update(db, db_obj=db_obj, obj_in=update_data)
            logger.info(f"Author updated successfully: {updated_author.name}")
            return updated_author
        except Exception as e:
            logger.error(f"Error updating author {db_obj.id}: {str(e)}")
            raise e

    def get_authors_with_book_count_filtered(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
        filters: Dict[str, Any] = None,
    ) -> List[Any]:
        """
        Get authors with book count and filtering capabilities.
        """
        query = (
            db.query(Author, func.count(Book.id).label("book_count"))
            .outerjoin(Book, Author.id == Book.author_id)
            .group_by(Author.id)
        )

        if filters:
            conditions = []

            # Search across name, bio, and nationality
            if "search" in filters and filters["search"]:
                search_term = f"%{filters['search']}%"
                search_conditions = [
                    Author.name.ilike(search_term),
                    Author.bio.ilike(search_term),
                    Author.nationality.ilike(search_term),
                ]
                conditions.append(or_(*search_conditions))

            # Filter by nationality
            if "nationality" in filters and filters["nationality"]:
                conditions.append(
                    Author.nationality.ilike(f"%{filters['nationality']}%")
                )

            # Filter by creation date range
            if "created_from" in filters and filters["created_from"]:
                conditions.append(Author.created_at >= filters["created_from"])

            if "created_to" in filters and filters["created_to"]:
                conditions.append(Author.created_at <= filters["created_to"])

            # Filter by birth date range
            if "birth_from" in filters and filters["birth_from"]:
                conditions.append(Author.birth_date >= filters["birth_from"])

            if "birth_to" in filters and filters["birth_to"]:
                conditions.append(Author.birth_date <= filters["birth_to"])

            # Apply all conditions
            if conditions:
                query = query.filter(and_(*conditions))

        return query.order_by(Author.id.desc()).offset(skip).limit(limit).all()

    def count_with_filters(self, db: Session, *, filters: Dict[str, Any] = None) -> int:
        """
        Count authors with filtering capabilities.
        """
        query = db.query(Author)

        if filters:
            conditions = []

            # Search across name, bio, and nationality
            if "search" in filters and filters["search"]:
                search_term = f"%{filters['search']}%"
                search_conditions = [
                    Author.name.ilike(search_term),
                    Author.bio.ilike(search_term),
                    Author.nationality.ilike(search_term),
                ]
                conditions.append(or_(*search_conditions))

            # Filter by nationality
            if "nationality" in filters and filters["nationality"]:
                conditions.append(
                    Author.nationality.ilike(f"%{filters['nationality']}%")
                )

            # Filter by creation date range
            if "created_from" in filters and filters["created_from"]:
                conditions.append(Author.created_at >= filters["created_from"])

            if "created_to" in filters and filters["created_to"]:
                conditions.append(Author.created_at <= filters["created_to"])

            # Filter by birth date range
            if "birth_from" in filters and filters["birth_from"]:
                conditions.append(Author.birth_date >= filters["birth_from"])

            if "birth_to" in filters and filters["birth_to"]:
                conditions.append(Author.birth_date <= filters["birth_to"])

            # Apply all conditions
            if conditions:
                query = query.filter(and_(*conditions))

        return query.count()

    # PUBLIC METHODS FOR USER SITE
    def get_public_authors(
        self, db: Session, *, skip: int = 0, limit: int = 100
    ) -> List[Author]:
        """Get authors for public access."""
        return db.query(Author).order_by(Author.name).offset(skip).limit(limit).all()

    def get_public_author(self, db: Session, *, id: int) -> Optional[Author]:
        """Get author by ID for public access."""
        return db.query(Author).filter(Author.id == id).first()

    def search_public_authors(
        self, db: Session, *, name: str, skip: int = 0, limit: int = 100
    ) -> List[Author]:
        """Search authors for public access."""
        return (
            db.query(Author)
            .filter(Author.name.ilike(f"%{name}%"))
            .order_by(Author.name)
            .offset(skip)
            .limit(limit)
            .all()
        )


crud_author = CRUDAuthor(Author)
