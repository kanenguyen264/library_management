from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
import logging

from app.user_site.schemas.book import Publisher
from app.user_site.repositories.publisher_repo import PublisherRepository
from app.user_site.repositories.book_repo import BookRepository
from app.core.exceptions import NotFoundException, ConflictException
from app.cache.decorators import cached, invalidate_cache
from app.common.utils.slug import generate_slug
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

# Logger for publisher service
logger = logging.getLogger(__name__)


async def get_all_publishers(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    search_query: Optional[str] = None,
    sort_by: str = "name",
    sort_desc: bool = False,
    admin_id: Optional[int] = None,
) -> List[Publisher]:
    """
    Get list of publishers with optional filtering.

    Args:
        db: Database session
        skip: Number of records to skip
        limit: Maximum number of records to return
        search_query: Search query
        sort_by: Field to sort by
        sort_desc: Sort in descending order if True
        admin_id: ID of the admin performing the action

    Returns:
        List of publishers
    """
    try:
        repo = PublisherRepository(db)
        publishers = await repo.list_publishers(
            skip=skip,
            limit=limit,
            search_query=search_query,
            sort_by=sort_by,
            sort_desc=sort_desc,
        )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="PUBLISHERS",
                        entity_id=0,
                        description="Viewed publisher list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "search_query": search_query,
                            "sort_by": sort_by,
                            "sort_desc": sort_desc,
                            "results_count": len(publishers),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return publishers
    except Exception as e:
        logger.error(f"Error retrieving publishers: {str(e)}")
        raise


async def count_publishers(db: Session, name: Optional[str] = None) -> int:
    """
    Count publishers matching filters.

    Args:
        db: Database session
        name: Filter by publisher name (partial match)

    Returns:
        Count of publishers matching the filters
    """
    try:
        repo = PublisherRepository(db)

        filters = {}
        if name:
            filters["name"] = name

        count = await repo.count(filters=filters)

        return count
    except Exception as e:
        logger.error(f"Error counting publishers: {str(e)}")
        raise


@cached(key_prefix="admin_publisher", ttl=300)
async def get_publisher_by_id(
    db: Session, publisher_id: int, admin_id: Optional[int] = None
) -> Publisher:
    """
    Get publisher details by ID.

    Args:
        db: Database session
        publisher_id: Publisher ID
        admin_id: ID of the admin performing the action

    Returns:
        Publisher details

    Raises:
        NotFoundException: If publisher not found
    """
    try:
        repo = PublisherRepository(db)
        publisher = await repo.get_by_id(publisher_id)

        if not publisher:
            logger.warning(f"Publisher with ID {publisher_id} not found")
            raise NotFoundException(
                detail=f"Publisher with ID {publisher_id} not found"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="PUBLISHER",
                        entity_id=publisher_id,
                        description=f"Viewed publisher details: {publisher.name}",
                        metadata={
                            "name": publisher.name,
                            "description": publisher.description,
                            "website": publisher.website,
                            "books_count": (
                                len(publisher.books)
                                if hasattr(publisher, "books")
                                else 0
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return publisher
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving publisher: {str(e)}")
        raise


@cached(key_prefix="admin_publisher_by_slug", ttl=300)
async def get_publisher_by_slug(db: Session, slug: str) -> Publisher:
    """
    Get publisher details by slug.

    Args:
        db: Database session
        slug: Publisher slug

    Returns:
        Publisher details

    Raises:
        NotFoundException: If publisher not found
    """
    try:
        repo = PublisherRepository(db)
        publisher = await repo.get_by_slug(slug)

        if not publisher:
            logger.warning(f"Publisher with slug '{slug}' not found")
            raise NotFoundException(detail=f"Publisher with slug '{slug}' not found")

        return publisher
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving publisher by slug: {str(e)}")
        raise


async def create_publisher(
    db: Session, publisher_data: Dict[str, Any], admin_id: Optional[int] = None
) -> Publisher:
    """
    Create a new publisher.

    Args:
        db: Database session
        publisher_data: Publisher data
        admin_id: ID of the admin performing the action

    Returns:
        Created publisher

    Raises:
        ConflictException: If publisher with same name already exists
    """
    try:
        repo = PublisherRepository(db)

        # Check if publisher with same name exists
        name = publisher_data.get("name")
        if name:
            existing = await repo.get_by_name(name)
            if existing:
                logger.warning(f"Publisher with name '{name}' already exists")
                raise ConflictException(
                    detail=f"Publisher with name '{name}' already exists"
                )

        # Generate slug if not provided
        if "slug" not in publisher_data and name:
            slug = generate_slug(name)
            publisher_data["slug"] = slug

        # Check if slug is unique
        if "slug" in publisher_data:
            existing_slug = await repo.get_by_slug(publisher_data["slug"])
            if existing_slug:
                logger.warning(
                    f"Publisher with slug '{publisher_data['slug']}' already exists"
                )
                raise ConflictException(
                    detail=f"Publisher with slug '{publisher_data['slug']}' already exists"
                )

        # Create publisher
        publisher = await repo.create(publisher_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="PUBLISHER",
                        entity_id=publisher.id,
                        description=f"Created new publisher: {publisher.name}",
                        metadata={
                            "name": publisher.name,
                            "description": publisher.description,
                            "website": publisher.website,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Created new publisher with ID {publisher.id}")
        return publisher
    except ConflictException:
        raise
    except Exception as e:
        logger.error(f"Error creating publisher: {str(e)}")
        raise


async def update_publisher(
    db: Session,
    publisher_id: int,
    publisher_data: Dict[str, Any],
    admin_id: Optional[int] = None,
) -> Publisher:
    """
    Update an existing publisher.

    Args:
        db: Database session
        publisher_id: Publisher ID
        publisher_data: Publisher data to update
        admin_id: ID of the admin performing the action

    Returns:
        Updated publisher

    Raises:
        NotFoundException: If publisher not found
        ConflictException: If publisher with same name already exists
    """
    try:
        # Check if publisher exists
        publisher = await get_publisher_by_id(db, publisher_id)

        repo = PublisherRepository(db)

        # Check if name is being updated and if it's unique
        if "name" in publisher_data and publisher_data["name"] != publisher.name:
            existing = await repo.get_by_name(publisher_data["name"])
            if existing and existing.id != publisher_id:
                logger.warning(
                    f"Publisher with name '{publisher_data['name']}' already exists"
                )
                raise ConflictException(
                    detail=f"Publisher with name '{publisher_data['name']}' already exists"
                )

            # If name changes, update slug if slug is not provided
            if "slug" not in publisher_data:
                publisher_data["slug"] = generate_slug(publisher_data["name"])

        # Check if slug is being updated and if it's unique
        if "slug" in publisher_data and publisher_data["slug"] != publisher.slug:
            existing_slug = await repo.get_by_slug(publisher_data["slug"])
            if existing_slug and existing_slug.id != publisher_id:
                logger.warning(
                    f"Publisher with slug '{publisher_data['slug']}' already exists"
                )
                raise ConflictException(
                    detail=f"Publisher with slug '{publisher_data['slug']}' already exists"
                )

        # Update publisher
        updated_publisher = await repo.update(publisher_id, publisher_data)

        # Xóa cache
        invalidate_cache(f"admin_publisher:{publisher_id}")

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="PUBLISHER",
                        entity_id=publisher_id,
                        description=f"Updated publisher: {updated_publisher.name}",
                        metadata={
                            "updated_fields": list(publisher_data.keys()),
                            "old_values": {
                                k: getattr(publisher, k) for k in publisher_data.keys()
                            },
                            "new_values": {
                                k: getattr(updated_publisher, k)
                                for k in publisher_data.keys()
                            },
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Updated publisher with ID {publisher_id}")
        return updated_publisher
    except NotFoundException:
        raise
    except ConflictException:
        raise
    except Exception as e:
        logger.error(f"Error updating publisher: {str(e)}")
        raise


async def delete_publisher(
    db: Session, publisher_id: int, admin_id: Optional[int] = None
) -> None:
    """
    Delete a publisher.

    Args:
        db: Database session
        publisher_id: Publisher ID
        admin_id: ID of the admin performing the action

    Raises:
        NotFoundException: If publisher not found
        ConflictException: If publisher has associated books
    """
    try:
        # Check if publisher exists
        publisher = await get_publisher_by_id(db, publisher_id)

        # Check if publisher has books
        book_repo = BookRepository(db)
        books_count = await book_repo.count(filters={"publisher_id": publisher_id})

        if books_count > 0:
            logger.warning(
                f"Cannot delete publisher {publisher_id} with {books_count} associated books"
            )
            raise ConflictException(
                detail=f"Cannot delete publisher with {books_count} associated books"
            )

        # Delete publisher
        repo = PublisherRepository(db)
        await repo.delete(publisher_id)

        # Xóa cache
        invalidate_cache(f"admin_publisher:{publisher_id}")

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="PUBLISHER",
                        entity_id=publisher_id,
                        description=f"Deleted publisher: {publisher.name}",
                        metadata={
                            "name": publisher.name,
                            "description": publisher.description,
                            "website": publisher.website,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Deleted publisher with ID {publisher_id}")
    except NotFoundException:
        raise
    except ConflictException:
        raise
    except Exception as e:
        logger.error(f"Error deleting publisher: {str(e)}")
        raise


@cached(key_prefix="admin_publisher_books", ttl=300)
async def get_publisher_books(
    db: Session,
    publisher_id: int,
    skip: int = 0,
    limit: int = 20,
    sort_by: str = "title",
    sort_desc: bool = False,
) -> List[Dict[str, Any]]:
    """
    Get books published by a specific publisher.

    Args:
        db: Database session
        publisher_id: Publisher ID
        skip: Number of records to skip
        limit: Maximum number of records to return
        sort_by: Field to sort by
        sort_desc: Sort in descending order if True

    Returns:
        List of books

    Raises:
        NotFoundException: If publisher not found
    """
    try:
        # Check if publisher exists
        publisher = await get_publisher_by_id(db, publisher_id)

        # Get books for this publisher
        book_repo = BookRepository(db)
        books = await book_repo.list(
            skip=skip,
            limit=limit,
            filters={"publisher_id": publisher_id},
            sort_by=sort_by,
            sort_desc=sort_desc,
        )

        return books
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving publisher books: {str(e)}")
        raise


async def count_publisher_books(db: Session, publisher_id: int) -> int:
    """
    Count books published by a specific publisher.

    Args:
        db: Database session
        publisher_id: Publisher ID

    Returns:
        Count of books

    Raises:
        NotFoundException: If publisher not found
    """
    try:
        # Check if publisher exists
        publisher = await get_publisher_by_id(db, publisher_id)

        # Count books for this publisher
        book_repo = BookRepository(db)
        count = await book_repo.count(filters={"publisher_id": publisher_id})

        return count
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error counting publisher books: {str(e)}")
        raise


@cached(key_prefix="admin_publisher_search", ttl=300)
async def search_publishers(
    db: Session, query: str, skip: int = 0, limit: int = 20
) -> List[Publisher]:
    """
    Search for publishers by name.

    Args:
        db: Database session
        query: Search query
        skip: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        List of matching publishers
    """
    try:
        repo = PublisherRepository(db)

        # Search is implemented in the repository
        publishers = await repo.search(query, skip, limit)

        return publishers
    except Exception as e:
        logger.error(f"Error searching publishers: {str(e)}")
        raise


@cached(key_prefix="admin_publisher_statistics", ttl=3600)
async def get_publisher_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get statistics about publishers.

    Args:
        db: Database session
        admin_id: ID of the admin performing the action

    Returns:
        Dictionary of publisher statistics
    """
    try:
        repo = PublisherRepository(db)
        book_repo = BookRepository(db)

        total = await repo.count_publishers()

        # Thống kê theo số lượng sách
        by_book_count = await repo.count_publishers_by_book_count()

        # Thống kê theo năm thành lập
        by_founding_year = await repo.count_publishers_by_founding_year()

        stats = {
            "total": total,
            "by_book_count": by_book_count,
            "by_founding_year": by_founding_year,
        }

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="PUBLISHER_STATISTICS",
                        entity_id=0,
                        description="Viewed publisher statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Error retrieving publisher statistics: {str(e)}")
        raise
