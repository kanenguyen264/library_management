"""
Database model utilities for SQLAlchemy models.

This module provides utilities for working with SQLAlchemy ORM models,
including a base model class with common methods for converting to/from dictionaries,
handling serialization, and performing common CRUD operations.
"""

from typing import (
    Dict,
    Any,
    TypeVar,
    Generic,
    List,
    Optional,
    Union,
    Type,
    Set,
    Callable,
)
from datetime import datetime, date
from uuid import UUID
import logging
import inspect

from sqlalchemy import inspect as sqlalchemy_inspect, func, Column, desc, asc
from sqlalchemy.exc import (
    SQLAlchemyError,
    IntegrityError,
    NoResultFound,
    MultipleResultsFound,
)
from sqlalchemy.orm import Session, RelationshipProperty, Query
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql.expression import cast, select
from sqlalchemy.types import String
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db.base_class import Base

# Use standard logging instead of the app's logger to avoid circular imports
logger = logging.getLogger(__name__)

# Type variable for the model class
T = TypeVar("T")


def model_to_dict(
    model: Any,
    exclude: List[str] = None,
    include_relationships: bool = False,
    max_depth: int = 1,
    _current_depth: int = 0,
    _seen_objects: Optional[Set[int]] = None,
) -> Dict[str, Any]:
    """
    Convert a SQLAlchemy model instance to a dictionary.

    Args:
        model: The SQLAlchemy model instance
        exclude: List of attribute names to exclude from the result
        include_relationships: Whether to include relationship attributes
        max_depth: Maximum depth for relationship traversal to prevent circular references
        _current_depth: Current depth in the relationship traversal (internal use)
        _seen_objects: Set of object IDs already processed to prevent circular references

    Returns:
        Dict containing model data, or None if model is None
    """
    if exclude is None:
        exclude = []

    if _seen_objects is None:
        _seen_objects = set()

    if model is None:
        return None

    # Check if we've seen this object before or reached max depth
    if _current_depth > max_depth:
        if hasattr(model, "id"):
            return {"id": getattr(model, "id", None)}
        return None

    # Try to get object ID to track seen objects
    obj_id = id(model)
    if obj_id in _seen_objects:
        if hasattr(model, "id"):
            return {"id": getattr(model, "id", None)}
        return None

    _seen_objects.add(obj_id)

    result = {}

    # Use SQLAlchemy inspect to get model attributes
    try:
        mapper = sqlalchemy_inspect(model)
    except Exception:
        # If not a SQLAlchemy model, try direct attribute access
        if hasattr(model, "__dict__"):
            for key, value in model.__dict__.items():
                if not key.startswith("_") and key not in exclude:
                    result[key] = _convert_value(value)
            return result
        return None

    # Process column attributes
    for column_attr in mapper.attrs:
        key = column_attr.key
        if key in exclude:
            continue

        if isinstance(column_attr, RelationshipProperty):
            # Handle relationships only if requested and not too deep
            if include_relationships and _current_depth < max_depth:
                try:
                    value = getattr(model, key)

                    # Handle collections (one-to-many, many-to-many)
                    if hasattr(value, "__iter__") and not isinstance(
                        value, (str, bytes, dict)
                    ):
                        # Check if we can access items in the collection
                        try:
                            result[key] = [
                                model_to_dict(
                                    item,
                                    exclude=exclude,
                                    include_relationships=include_relationships,
                                    max_depth=max_depth,
                                    _current_depth=_current_depth + 1,
                                    _seen_objects=_seen_objects.copy(),
                                )
                                for item in value
                                if item is not None
                            ]
                        except (TypeError, AttributeError):
                            # If we can't iterate, store as is
                            result[key] = str(value)
                    else:
                        # Handle scalar relationships (many-to-one, one-to-one)
                        result[key] = model_to_dict(
                            value,
                            exclude=exclude,
                            include_relationships=include_relationships,
                            max_depth=max_depth,
                            _current_depth=_current_depth + 1,
                            _seen_objects=_seen_objects.copy(),
                        )
                except Exception as e:
                    # Log error but continue processing other attributes
                    logger.debug(f"Error processing relationship {key}: {str(e)}")
                    result[key] = None
        else:
            # Handle regular attributes
            try:
                value = getattr(model, key)
                result[key] = _convert_value(value)
            except Exception as e:
                logger.debug(f"Error getting attribute {key}: {str(e)}")
                result[key] = None

    return result


def _convert_value(value: Any) -> Any:
    """
    Convert a value to a JSON-serializable type.

    Args:
        value: The value to convert

    Returns:
        Converted value
    """
    # Handle date and datetime objects
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    # Handle UUID objects
    elif isinstance(value, UUID):
        return str(value)
    # Handle SQLAlchemy InstrumentedList and other iterables
    elif hasattr(value, "__iter__") and not isinstance(value, (str, bytes, dict)):
        try:
            return [_convert_value(item) for item in value]
        except (TypeError, AttributeError):
            return str(value)
    # Handle simple types
    elif isinstance(value, (str, int, float, bool, type(None))):
        return value
    # Handle objects with __dict__
    elif hasattr(value, "__dict__"):
        return str(value)
    # Default fallback
    else:
        return str(value)


class Model(Generic[T]):
    """
    Generic model class with common database operations.

    This class provides a generic interface for common database
    operations on SQLAlchemy models.
    """

    def __init__(self, db: Union[Session, AsyncSession], model_class: Type[T]):
        """
        Initialize the model with a database session and model class.

        Args:
            db: SQLAlchemy database session (sync or async)
            model_class: The model class to operate on
        """
        self.db = db
        self.model_class = model_class
        self.is_async = isinstance(db, AsyncSession)

    def _wrap_method_for_async(self, method: Callable, *args, **kwargs) -> Callable:
        """
        Create a wrapper for synchronous methods to use in async context.

        Args:
            method: The method to wrap
            *args: Arguments to pass to the method
            **kwargs: Keyword arguments to pass to the method

        Returns:
            Wrapped method
        """

        async def async_wrapper(session):
            return method(session, *args, **kwargs)

        return async_wrapper

    async def _execute_async(self, func, *args, **kwargs):
        """
        Execute a function in async context safely, handling both scalar and query results.

        Args:
            func: Function to run
            *args: Arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function

        Returns:
            Result of the function
        """
        if not self.is_async:
            return func(self.db, *args, **kwargs)

        try:
            # For SQLAlchemy 1.4+, we need to handle differently based on return type
            method_wrapper = self._wrap_method_for_async(func, *args, **kwargs)

            # Try to determine if this is a query that should use execute() or a method to use run_sync()
            # This is a heuristic and might need adjustments
            source = inspect.getsource(func).lower()

            if "query" in source or "select" in source:
                # For queries, prefer execute
                result = await self.db.execute(method_wrapper)
                # Try to detect if this is a scalar or a collection
                if (
                    "first" in source
                    or "scalar" in source
                    or "get" in source
                    and not "get_multi" in source
                ):
                    return result.scalar_one_or_none()
                else:
                    return result.scalars().all()
            else:
                # For other operations, use run_sync
                return await self.db.run_sync(
                    lambda session: func(session, *args, **kwargs)
                )
        except Exception as e:
            logger.error(f"Error in async execution: {str(e)}")
            raise

    def create(self, obj_in: Dict[str, Any]) -> T:
        """
        Create a new record in the database.

        Args:
            obj_in: Dictionary with model data

        Returns:
            Created model instance

        Raises:
            IntegrityError: If there's a constraint violation
            SQLAlchemyError: For other database errors
        """
        try:
            db_obj = self.model_class(**obj_in)
            self.db.add(db_obj)
            self.db.commit()
            self.db.refresh(db_obj)
            return db_obj
        except IntegrityError as e:
            self.db.rollback()
            logger.error(
                f"Integrity error creating {self.model_class.__name__}: {str(e)}"
            )
            raise
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error creating {self.model_class.__name__}: {str(e)}")
            raise

    async def create_async(self, obj_in: Dict[str, Any]) -> T:
        """
        Create a new record in the database asynchronously.

        Args:
            obj_in: Dictionary with model data

        Returns:
            Created model instance

        Raises:
            IntegrityError: If there's a constraint violation
            SQLAlchemyError: For other database errors
        """
        if not self.is_async:
            logger.warning(
                "Using create_async with a non-async session. Falling back to sync method."
            )
            return self.create(obj_in)

        try:
            db_obj = self.model_class(**obj_in)
            self.db.add(db_obj)
            await self.db.commit()
            await self.db.refresh(db_obj)
            return db_obj
        except IntegrityError as e:
            await self.db.rollback()
            logger.error(
                f"Integrity error creating {self.model_class.__name__}: {str(e)}"
            )
            raise
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Error creating {self.model_class.__name__}: {str(e)}")
            raise
        except Exception as e:
            # Catch other exceptions that might occur in async context
            if hasattr(self.db, "rollback"):
                if self.is_async:
                    await self.db.rollback()
                else:
                    self.db.rollback()
            logger.error(f"Unexpected error in create_async: {str(e)}")
            raise

    def _get(self, session, id: Any) -> Optional[T]:
        """Internal method to get a record by ID."""
        return session.query(self.model_class).filter(self.model_class.id == id).first()

    def get(self, id: Any) -> Optional[T]:
        """
        Get a record by ID.

        Args:
            id: The ID of the record

        Returns:
            Model instance if found, None otherwise
        """
        return self._get(self.db, id)

    async def get_async(self, id: Any) -> Optional[T]:
        """
        Get a record by ID asynchronously.

        Args:
            id: The ID of the record

        Returns:
            Model instance if found, None otherwise
        """
        if not self.is_async:
            logger.warning(
                "Using get_async with a non-async session. Falling back to sync method."
            )
            return self.get(id)

        try:
            # Create a specialized version for get to avoid issues with exec
            async def _get_by_id(session):
                stmt = select(self.model_class).where(self.model_class.id == id)
                result = await session.execute(stmt)
                return result.scalar_one_or_none()

            return await _get_by_id(self.db)
        except Exception as e:
            logger.error(f"Error in get_async: {str(e)}")
            raise

    def _get_multi(
        self,
        session,
        skip: int = 0,
        limit: int = 100,
        filters: Dict[str, Any] = None,
        order_by: str = None,
        descending: bool = False,
    ) -> List[T]:
        """Internal method to get multiple records."""
        query = session.query(self.model_class)

        if filters:
            for key, value in filters.items():
                if hasattr(self.model_class, key):
                    if value is not None:
                        # Handle list values for IN operations
                        if isinstance(value, (list, tuple, set)):
                            query = query.filter(
                                getattr(self.model_class, key).in_(value)
                            )
                        else:
                            query = query.filter(
                                getattr(self.model_class, key) == value
                            )

        if order_by and hasattr(self.model_class, order_by):
            column = getattr(self.model_class, order_by)
            query = query.order_by(desc(column) if descending else asc(column))

        return query.offset(skip).limit(limit).all()

    def get_multi(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Dict[str, Any] = None,
        order_by: str = None,
        descending: bool = False,
    ) -> List[T]:
        """
        Get multiple records with pagination and filtering.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            filters: Dictionary of filters to apply
            order_by: Column name to order by
            descending: Whether to order in descending order

        Returns:
            List of model instances
        """
        return self._get_multi(self.db, skip, limit, filters, order_by, descending)

    async def get_multi_async(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Dict[str, Any] = None,
        order_by: str = None,
        descending: bool = False,
    ) -> List[T]:
        """
        Get multiple records with pagination and filtering asynchronously.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            filters: Dictionary of filters to apply
            order_by: Column name to order by
            descending: Whether to order in descending order

        Returns:
            List of model instances
        """
        if not self.is_async:
            logger.warning(
                "Using get_multi_async with a non-async session. Falling back to sync method."
            )
            return self.get_multi(skip, limit, filters, order_by, descending)

        try:
            # Create a specialized async query for get_multi
            async def _get_multi_query(session):
                stmt = select(self.model_class)

                # Apply filters
                if filters:
                    for key, value in filters.items():
                        if hasattr(self.model_class, key):
                            if value is not None:
                                if isinstance(value, (list, tuple, set)):
                                    stmt = stmt.where(
                                        getattr(self.model_class, key).in_(value)
                                    )
                                else:
                                    stmt = stmt.where(
                                        getattr(self.model_class, key) == value
                                    )

                # Apply ordering
                if order_by and hasattr(self.model_class, order_by):
                    column = getattr(self.model_class, order_by)
                    if descending:
                        stmt = stmt.order_by(desc(column))
                    else:
                        stmt = stmt.order_by(asc(column))

                # Apply pagination
                stmt = stmt.offset(skip).limit(limit)

                # Execute query
                result = await session.execute(stmt)
                return result.scalars().all()

            return await _get_multi_query(self.db)
        except Exception as e:
            logger.error(f"Error in get_multi_async: {str(e)}")
            raise

    def _update(self, session, id: Any, obj_in: Dict[str, Any]) -> Optional[T]:
        """Internal method to update a record."""
        db_obj = self._get(session, id)
        if db_obj:
            for key, value in obj_in.items():
                if hasattr(db_obj, key):
                    setattr(db_obj, key, value)

            session.add(db_obj)
            session.commit()
            session.refresh(db_obj)
        return db_obj

    def update(self, id: Any, obj_in: Dict[str, Any]) -> Optional[T]:
        """
        Update a record by ID.

        Args:
            id: The ID of the record to update
            obj_in: Dictionary with updated data

        Returns:
            Updated model instance if found, None otherwise

        Raises:
            IntegrityError: If there's a constraint violation
            SQLAlchemyError: For other database errors
        """
        try:
            return self._update(self.db, id, obj_in)
        except IntegrityError as e:
            self.db.rollback()
            logger.error(
                f"Integrity error updating {self.model_class.__name__}: {str(e)}"
            )
            raise
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error updating {self.model_class.__name__}: {str(e)}")
            raise

    async def update_async(self, id: Any, obj_in: Dict[str, Any]) -> Optional[T]:
        """
        Update a record by ID asynchronously.

        Args:
            id: The ID of the record to update
            obj_in: Dictionary with updated data

        Returns:
            Updated model instance if found, None otherwise

        Raises:
            IntegrityError: If there's a constraint violation
            SQLAlchemyError: For other database errors
        """
        if not self.is_async:
            logger.warning(
                "Using update_async with a non-async session. Falling back to sync method."
            )
            return self.update(id, obj_in)

        try:
            # Specialized async update implementation to avoid _run_async issues
            async def _update_by_id(session):
                # Get the object first
                stmt = select(self.model_class).where(self.model_class.id == id)
                result = await session.execute(stmt)
                db_obj = result.scalar_one_or_none()

                if not db_obj:
                    return None

                # Update attributes
                for key, value in obj_in.items():
                    if hasattr(db_obj, key):
                        setattr(db_obj, key, value)

                # Commit changes
                session.add(db_obj)
                await session.commit()
                await session.refresh(db_obj)
                return db_obj

            return await _update_by_id(self.db)
        except IntegrityError as e:
            await self.db.rollback()
            logger.error(
                f"Integrity error updating {self.model_class.__name__}: {str(e)}"
            )
            raise
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Error updating {self.model_class.__name__}: {str(e)}")
            raise
        except Exception as e:
            # Catch other exceptions that might occur in async context
            if hasattr(self.db, "rollback"):
                await self.db.rollback()
            logger.error(f"Unexpected error in update_async: {str(e)}")
            raise

    def _delete(self, session, id: Any) -> bool:
        """Internal method to delete a record."""
        db_obj = self._get(session, id)
        if db_obj:
            session.delete(db_obj)
            session.commit()
            return True
        return False

    def delete(self, id: Any) -> bool:
        """
        Delete a record by ID.

        Args:
            id: The ID of the record to delete

        Returns:
            True if the record was deleted, False otherwise

        Raises:
            SQLAlchemyError: For database errors
        """
        try:
            return self._delete(self.db, id)
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error deleting {self.model_class.__name__}: {str(e)}")
            raise

    async def delete_async(self, id: Any) -> bool:
        """
        Delete a record by ID asynchronously.

        Args:
            id: The ID of the record to delete

        Returns:
            True if the record was deleted, False otherwise

        Raises:
            SQLAlchemyError: For database errors
        """
        if not self.is_async:
            logger.warning(
                "Using delete_async with a non-async session. Falling back to sync method."
            )
            return self.delete(id)

        try:
            # Specialized async delete implementation
            async def _delete_by_id(session):
                # Get the object first
                stmt = select(self.model_class).where(self.model_class.id == id)
                result = await session.execute(stmt)
                db_obj = result.scalar_one_or_none()

                if not db_obj:
                    return False

                # Delete the object
                await session.delete(db_obj)
                await session.commit()
                return True

            return await _delete_by_id(self.db)
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Error deleting {self.model_class.__name__}: {str(e)}")
            raise
        except Exception as e:
            # Catch other exceptions that might occur in async context
            if hasattr(self.db, "rollback"):
                await self.db.rollback()
            logger.error(f"Unexpected error in delete_async: {str(e)}")
            raise

    def _count(self, session, filters: Dict[str, Any] = None) -> int:
        """Internal method to count records."""
        query = session.query(func.count(self.model_class.id))

        if filters:
            for key, value in filters.items():
                if hasattr(self.model_class, key):
                    if value is not None:
                        if isinstance(value, (list, tuple, set)):
                            query = query.filter(
                                getattr(self.model_class, key).in_(value)
                            )
                        else:
                            query = query.filter(
                                getattr(self.model_class, key) == value
                            )

        return query.scalar() or 0

    def count(self, filters: Dict[str, Any] = None) -> int:
        """
        Count records with optional filtering.

        Args:
            filters: Dictionary of filters to apply

        Returns:
            Number of records
        """
        return self._count(self.db, filters)

    async def count_async(self, filters: Dict[str, Any] = None) -> int:
        """
        Count records with optional filtering asynchronously.

        Args:
            filters: Dictionary of filters to apply

        Returns:
            Number of records
        """
        if not self.is_async:
            logger.warning(
                "Using count_async with a non-async session. Falling back to sync method."
            )
            return self.count(filters)

        try:
            # Specialized async count implementation
            async def _count_query(session):
                stmt = select(func.count(self.model_class.id))

                # Apply filters
                if filters:
                    for key, value in filters.items():
                        if hasattr(self.model_class, key):
                            if value is not None:
                                if isinstance(value, (list, tuple, set)):
                                    stmt = stmt.where(
                                        getattr(self.model_class, key).in_(value)
                                    )
                                else:
                                    stmt = stmt.where(
                                        getattr(self.model_class, key) == value
                                    )

                # Execute query
                result = await session.execute(stmt)
                return result.scalar_one() or 0

            return await _count_query(self.db)
        except Exception as e:
            logger.error(f"Error in count_async: {str(e)}")
            raise

    def _exists(self, session, filters: Dict[str, Any]) -> bool:
        """Internal method to check if a record exists."""
        query = session.query(self.model_class)

        for key, value in filters.items():
            if hasattr(self.model_class, key):
                if value is not None:
                    query = query.filter(getattr(self.model_class, key) == value)

        return session.query(query.exists()).scalar()

    def exists(self, filters: Dict[str, Any]) -> bool:
        """
        Check if any record exists with the given filters.

        Args:
            filters: Dictionary of filters to apply

        Returns:
            True if a record exists, False otherwise
        """
        return self._exists(self.db, filters)

    async def exists_async(self, filters: Dict[str, Any]) -> bool:
        """
        Check if any record exists with the given filters asynchronously.

        Args:
            filters: Dictionary of filters to apply

        Returns:
            True if a record exists, False otherwise
        """
        if not self.is_async:
            logger.warning(
                "Using exists_async with a non-async session. Falling back to sync method."
            )
            return self.exists(filters)

        try:
            # Specialized async exists implementation
            async def _exists_query(session):
                # Build base query
                subquery = select(self.model_class)

                # Apply filters
                for key, value in filters.items():
                    if hasattr(self.model_class, key):
                        if value is not None:
                            subquery = subquery.where(
                                getattr(self.model_class, key) == value
                            )

                # Execute exists query
                stmt = select(func.count()).where(subquery.exists())
                result = await session.execute(stmt)
                return result.scalar_one() > 0

            return await _exists_query(self.db)
        except Exception as e:
            logger.error(f"Error in exists_async: {str(e)}")
            raise

    def _search(
        self,
        session,
        search_term: str,
        fields: List[str],
        skip: int = 0,
        limit: int = 100,
    ) -> List[T]:
        """Internal method to search for records."""
        query = session.query(self.model_class)
        search_term = f"%{search_term}%"

        # Build OR conditions for each field
        from sqlalchemy import or_

        conditions = []

        for field in fields:
            if hasattr(self.model_class, field):
                attr = getattr(self.model_class, field)
                # Convert to string for comparison if needed
                conditions.append(cast(attr, String).ilike(search_term))

        if conditions:
            query = query.filter(or_(*conditions))

        return query.offset(skip).limit(limit).all()

    def search(
        self, search_term: str, fields: List[str], skip: int = 0, limit: int = 100
    ) -> List[T]:
        """
        Search for records by a search term in specified fields.

        Args:
            search_term: The search term
            fields: List of field names to search in
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of model instances matching the search
        """
        return self._search(self.db, search_term, fields, skip, limit)

    async def search_async(
        self, search_term: str, fields: List[str], skip: int = 0, limit: int = 100
    ) -> List[T]:
        """
        Search for records by a search term in specified fields asynchronously.

        Args:
            search_term: The search term
            fields: List of field names to search in
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of model instances matching the search
        """
        if not self.is_async:
            logger.warning(
                "Using search_async with a non-async session. Falling back to sync method."
            )
            return self.search(search_term, fields, skip, limit)

        try:
            # Specialized async search implementation
            async def _search_query(session):
                from sqlalchemy import or_

                # Create base query
                stmt = select(self.model_class)
                search_pattern = f"%{search_term}%"

                # Build search conditions
                conditions = []
                for field in fields:
                    if hasattr(self.model_class, field):
                        attr = getattr(self.model_class, field)
                        conditions.append(cast(attr, String).ilike(search_pattern))

                # Apply search conditions
                if conditions:
                    stmt = stmt.where(or_(*conditions))

                # Apply pagination
                stmt = stmt.offset(skip).limit(limit)

                # Execute query
                result = await session.execute(stmt)
                return result.scalars().all()

            return await _search_query(self.db)
        except Exception as e:
            logger.error(f"Error in search_async: {str(e)}")
            raise
