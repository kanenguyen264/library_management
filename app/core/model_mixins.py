"""
Model mixins for SQLAlchemy models.

This module contains reusable mixins that can be applied to ORM models.
"""

from datetime import datetime
import json
import hashlib
from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, func, event
from app.core.config import get_settings
from app.core.event import EventSystem, BookEvent, publish_book_event

settings = get_settings()


class TimestampMixin:
    """Mixin for timestamp functionality."""

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    def update_timestamp(self):
        """Update the updated_at timestamp."""
        self.updated_at = func.now()


class SoftDeleteMixin:
    """Mixin for soft delete functionality."""

    is_deleted = Column(Boolean, default=False, index=True)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(Integer, nullable=True)

    def soft_delete(self, user_id=None):
        """Mark the record as deleted."""
        self.is_deleted = True
        self.deleted_at = func.now()
        self.deleted_by = user_id

    def restore(self):
        """Restore a soft-deleted record"""
        self.is_deleted = False
        self.deleted_at = None

    @property
    def is_deleted(self):
        """Check if record is soft deleted"""
        return self.deleted_at is not None


class AuditMixin:
    """Mixin for auditing changes to models."""

    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)
    creation_ip = Column(String(50), nullable=True)
    update_ip = Column(String(50), nullable=True)
    created_by_id = Column(Integer, nullable=True)
    updated_by_id = Column(Integer, nullable=True)

    def track_creation(self, user_id, ip_address):
        """Track creation details."""
        self.created_by = user_id
        self.creation_ip = ip_address

    def track_update(self, user_id, ip_address):
        """Track update details."""
        self.updated_by = user_id
        self.update_ip = ip_address

    def update_audit_fields(self, user_id=None):
        """Update the audit fields with current user"""
        self.updated_at = func.now()
        if user_id is not None:
            self.updated_by_id = user_id


class VersioningMixin:
    """Mixin for versioning model data."""

    version = Column(Integer, default=1)
    version_changes = Column(JSON, nullable=True)

    def increment_version(self, change_data=None):
        """Increment the version number and store the change information"""
        self.version = (self.version or 0) + 1

        if change_data:
            # Initialize version_changes if it doesn't exist
            if not self.version_changes:
                self.version_changes = {}

            # Store changes with version number as key
            self.version_changes[str(self.version)] = {
                "timestamp": datetime.now().isoformat(),
                "changes": change_data,
            }

        return self.version

    @property
    def version_history(self):
        """Get the version history in a more user-friendly format"""
        if not self.version_changes:
            return []

        history = []
        for version, data in self.version_changes.items():
            entry = {
                "version": int(version),
                "timestamp": data.get("timestamp"),
                "changes": data.get("changes", {}),
            }
            history.append(entry)

        # Sort by version number descending (newest first)
        return sorted(history, key=lambda x: x["version"], reverse=True)


class CacheMixin:
    """Mixin for cache-related functionality."""

    cache_key = Column(String(64), nullable=True, index=True)
    cache_updated_at = Column(DateTime, nullable=True)

    def update_cache_key(self):
        """Generate and update a unique cache key based on object state"""
        try:
            # Create a representation of the object's state
            state_dict = {
                c.name: getattr(self, c.name)
                for c in self.__table__.columns
                if c.name not in ["cache_key", "cache_updated_at"]
            }

            # Add class name to make it unique across different models
            state_dict["__class__"] = self.__class__.__name__

            # Add timestamp to ensure uniqueness
            state_dict["__timestamp__"] = datetime.now().isoformat()

            # Convert to JSON string and create hash
            state_str = json.dumps(state_dict, sort_keys=True, default=str)
            hash_obj = hashlib.sha256(state_str.encode())
            self.cache_key = hash_obj.hexdigest()
            self.cache_updated_at = func.now()

            return self.cache_key
        except Exception:
            # Fallback to timestamp-based key if anything fails
            self.cache_key = (
                f"{self.__class__.__name__}_{self.id}_{int(datetime.now().timestamp())}"
            )
            self.cache_updated_at = func.now()
            return self.cache_key

    @property
    def cache_age_seconds(self):
        """Get the age of the cache in seconds"""
        if not self.cache_updated_at:
            return None
        return (datetime.now() - self.cache_updated_at).total_seconds()

    def is_cache_valid(self, max_age_seconds=3600):
        """Check if the cached data is still valid based on age"""
        if not self.cache_updated_at:
            return False
        age = self.cache_age_seconds
        return age is not None and age <= max_age_seconds


class RateLimitMixin:
    """Mixin for rate limiting functionality."""

    rate_limit_tier = Column(String(20), default="standard")
    last_rate_limit_update = Column(DateTime, nullable=True)
    last_action_at = Column(DateTime, nullable=True)
    action_count = Column(Integer, default=0)

    def get_rate_limit(self):
        """Get the rate limit for this model based on tier."""
        limits = {
            "standard": settings.RATE_LIMIT_REQUESTS,
            "premium": settings.RATE_LIMIT_REQUESTS * 2,
            "unlimited": 0,  # No limit
        }
        return limits.get(self.rate_limit_tier, settings.RATE_LIMIT_REQUESTS)

    def register_action(self, reset_after_hours=24):
        """Register an action for rate limiting purposes"""
        now = datetime.now()

        # If this is first action or last action was more than reset period ago, reset counter
        if (
            self.last_action_at is None
            or (now - self.last_action_at).total_seconds() > reset_after_hours * 3600
        ):
            self.action_count = 1
        else:
            self.action_count += 1

        self.last_action_at = now
        return self.action_count

    def can_perform_action(self, max_actions=5, period_hours=24):
        """Check if more actions are allowed based on rate limits"""
        if self.last_action_at is None:
            return True

        now = datetime.now()
        # If last action was more than period ago, reset counter implicitly
        if (now - self.last_action_at).total_seconds() > period_hours * 3600:
            return True

        # Otherwise, check against max_actions
        return self.action_count < max_actions


class TracingMixin:
    """Mixin for OpenTelemetry tracing."""

    last_activity_trace_id = Column(String(64), nullable=True)

    def set_trace_id(self, trace_id):
        """Set the OpenTelemetry trace ID."""
        self.last_activity_trace_id = trace_id


class EventMixin:
    """
    Mixin that provides event-based functionality to models.
    Allows models to publish events when certain actions occur.
    """

    def register_event(self, event_name: str, callback) -> None:
        """
        Register a callback for a specific event on this model

        Args:
            event_name: The name of the event to subscribe to
            callback: The function to call when the event is triggered
        """
        EventSystem.subscribe(event_name, callback)

    def unregister_event(self, event_name: str, callback) -> bool:
        """
        Unregister a callback for a specific event on this model

        Args:
            event_name: The name of the event
            callback: The function to unsubscribe

        Returns:
            bool: True if unsubscribed successfully, False otherwise
        """
        return EventSystem.unsubscribe(event_name, callback)

    def publish_event(self, event_name: str, **kwargs) -> int:
        """
        Publish an event from this model

        Args:
            event_name: The name of the event to publish
            **kwargs: Additional data to pass to the subscribers

        Returns:
            int: Number of subscribers notified
        """
        # Make sure the model ID is passed to the event
        if hasattr(self, "id"):
            kwargs["model_id"] = self.id

        # Additional model data can be included
        if hasattr(self, "to_dict"):
            kwargs["model_data"] = self.to_dict()

        return EventSystem.publish(event_name, **kwargs)

    def publish_book_event(self, event_name: str, **kwargs) -> int:
        """
        Publish a predefined book event

        Args:
            event_name: One of the event names defined in BookEvent
            **kwargs: Additional data to pass to the subscribers

        Returns:
            int: Number of subscribers notified
        """
        if not hasattr(self, "id"):
            raise AttributeError(
                "Model must have an 'id' attribute to publish book events"
            )

        return publish_book_event(event_name, self.id, **kwargs)


# Create event listeners for the mixins
def register_mixin_events():
    """Register SQLAlchemy events for mixins."""
    from app.core.db import Base

    @event.listens_for(Base, "after_update")
    def update_cache_key(mapper, connection, target):
        if hasattr(target, "cache_key") and hasattr(target, "update_cache_key"):
            target.update_cache_key()
