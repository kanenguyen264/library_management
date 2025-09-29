"""
Database event handlers for SQLAlchemy models.

This module contains event listeners that are attached to SQLAlchemy models
to handle auditing, caching, and other cross-cutting concerns.
"""

from sqlalchemy import event
from app.core.db import Base
from app.logging.setup import get_logger

logger = get_logger(__name__)

try:
    from app.logs_manager.services import create_audit_log
    from app.cache.manager import cache_manager

    HAS_AUDIT_LOG = True
    HAS_CACHE_MANAGER = True
except ImportError:
    logger.warning(
        "Could not import audit_log or cache_manager, some features will be disabled"
    )
    HAS_AUDIT_LOG = False
    HAS_CACHE_MANAGER = False


def register_events():
    """Register all database events."""

    # Event: After Insert
    @event.listens_for(Base, "after_insert")
    def log_model_insert(mapper, connection, target):
        """Log model creation events to audit log."""
        if not HAS_AUDIT_LOG:
            return

        # Skip certain models or tables to prevent recursion
        if hasattr(target, "__tablename__") and target.__tablename__ in [
            "audit_logs",
            "error_logs",
            "system_logs",
        ]:
            return

        try:
            # Create audit log entry - this will be executed asynchronously later
            # because the current connection is being used in the transaction
            if hasattr(target, "to_dict"):
                data = target.to_dict()

                # Get current user ID if available
                user_id = getattr(target, "created_by", None)

                create_audit_log(
                    db=None,  # Will be provided by the async executor
                    action="CREATE",
                    resource_type=target.__tablename__,
                    resource_id=target.id if hasattr(target, "id") else None,
                    user_id=user_id,
                    old_values={},
                    new_values=data,
                )
        except Exception as e:
            logger.error(f"Error logging model insert: {str(e)}")

    # Event: After Update
    @event.listens_for(Base, "after_update")
    def log_model_update(mapper, connection, target):
        """Log model update events to audit log."""
        if not HAS_AUDIT_LOG:
            return

        # Skip certain models
        if hasattr(target, "__tablename__") and target.__tablename__ in [
            "audit_logs",
            "error_logs",
            "system_logs",
        ]:
            return

        try:
            # Only log if there are changes
            if hasattr(target, "to_dict"):
                # Get current user ID if available
                user_id = getattr(target, "updated_by", None)

                create_audit_log(
                    db=None,
                    action="UPDATE",
                    resource_type=target.__tablename__,
                    resource_id=target.id if hasattr(target, "id") else None,
                    user_id=user_id,
                    old_values={},  # We don't have the old values in this context
                    new_values=target.to_dict(),
                )
        except Exception as e:
            logger.error(f"Error logging model update: {str(e)}")

    # Event: After Delete
    @event.listens_for(Base, "after_delete")
    def log_model_delete(mapper, connection, target):
        """Log model deletion events to audit log."""
        if not HAS_AUDIT_LOG:
            return

        # Skip certain models
        if hasattr(target, "__tablename__") and target.__tablename__ in [
            "audit_logs",
            "error_logs",
            "system_logs",
        ]:
            return

        try:
            # Get current user ID if available
            user_id = getattr(target, "deleted_by", None)

            create_audit_log(
                db=None,
                action="DELETE",
                resource_type=target.__tablename__,
                resource_id=target.id if hasattr(target, "id") else None,
                user_id=user_id,
                old_values=target.to_dict() if hasattr(target, "to_dict") else {},
                new_values={},
            )
        except Exception as e:
            logger.error(f"Error logging model delete: {str(e)}")

    # Event: After Update - Cache invalidation
    @event.listens_for(Base, "after_update")
    def invalidate_cache(mapper, connection, target):
        """Invalidate cache entries related to the updated model."""
        if not HAS_CACHE_MANAGER:
            return

        try:
            # Create cache pattern based on model name and ID
            if hasattr(target, "__tablename__") and hasattr(target, "id"):
                pattern = f"{target.__tablename__}:{target.id}:*"

                # This will be executed asynchronously
                cache_manager.invalidate_pattern(pattern)

                # Update cache key if applicable
                if hasattr(target, "cache_key") and hasattr(target, "update_cache_key"):
                    target.update_cache_key()
        except Exception as e:
            logger.error(f"Error invalidating cache: {str(e)}")

    # Register other events as needed

    logger.info("Database event handlers registered")
