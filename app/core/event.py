from typing import Dict, List, Callable, Any
import logging

logger = logging.getLogger(__name__)


class EventSystem:
    """
    A simple event system to support publish-subscribe pattern
    """

    _subscribers: Dict[str, List[Callable]] = {}

    @classmethod
    def subscribe(cls, event_name: str, callback: Callable) -> None:
        """
        Subscribe a callback function to an event

        Args:
            event_name: The name of the event to subscribe to
            callback: The function to call when the event is triggered
        """
        if event_name not in cls._subscribers:
            cls._subscribers[event_name] = []

        cls._subscribers[event_name].append(callback)
        logger.debug(f"Subscribed to event '{event_name}'")

    @classmethod
    def unsubscribe(cls, event_name: str, callback: Callable) -> bool:
        """
        Unsubscribe a callback function from an event

        Args:
            event_name: The name of the event
            callback: The function to unsubscribe

        Returns:
            bool: True if unsubscribed successfully, False otherwise
        """
        if event_name not in cls._subscribers:
            return False

        try:
            cls._subscribers[event_name].remove(callback)
            logger.debug(f"Unsubscribed from event '{event_name}'")
            return True
        except ValueError:
            return False

    @classmethod
    def publish(cls, event_name: str, **kwargs) -> int:
        """
        Publish an event to all subscribers

        Args:
            event_name: The name of the event to publish
            **kwargs: Additional data to pass to the subscribers

        Returns:
            int: Number of subscribers notified
        """
        if event_name not in cls._subscribers:
            return 0

        count = 0
        for callback in cls._subscribers[event_name]:
            try:
                callback(**kwargs)
                count += 1
            except Exception as e:
                logger.error(f"Error in event subscriber for '{event_name}': {str(e)}")

        logger.debug(f"Published event '{event_name}' to {count} subscribers")
        return count


# Predefined event names for book-related events
class BookEvent:
    PUBLISHED = "book.published"
    UNPUBLISHED = "book.unpublished"
    UPDATED = "book.updated"
    POPULARITY_CHANGED = "book.popularity_changed"
    RATING_CHANGED = "book.rating_changed"


# Predefined event names for chapter-related events
class ChapterEvent:
    PUBLISHED = "chapter.published"
    UNPUBLISHED = "chapter.unpublished"
    UPDATED = "chapter.updated"
    VIEWED = "chapter.viewed"


# Predefined event names for user-related events
class UserEvent:
    REGISTERED = "user.registered"
    LOGGED_IN = "user.logged_in"
    PROFILE_UPDATED = "user.profile_updated"
    PREMIUM_CHANGED = "user.premium_changed"
    PASSWORD_CHANGED = "user.password_changed"


# Predefined event names for review-related events
class ReviewEvent:
    CREATED = "review.created"
    UPDATED = "review.updated"
    DELETED = "review.deleted"
    REPORTED = "review.reported"
    APPROVED = "review.approved"
    REJECTED = "review.rejected"


# Predefined event names for reading-related events
class ReadingEvent:
    STARTED = "reading.started"
    PROGRESSED = "reading.progressed"
    COMPLETED = "reading.completed"
    SESSION_STARTED = "reading.session_started"
    SESSION_ENDED = "reading.session_ended"


# Predefined event names for discussion-related events
class DiscussionEvent:
    CREATED = "discussion.created"
    UPDATED = "discussion.updated"
    DELETED = "discussion.deleted"
    COMMENT_ADDED = "discussion.comment_added"
    PINNED = "discussion.pinned"
    UNPINNED = "discussion.unpinned"


# Convenience function to publish book events
def publish_book_event(event_name: str, book_id: int, **kwargs) -> int:
    """
    Publish a book-related event

    Args:
        event_name: The name of the event from BookEvent class
        book_id: The ID of the book
        **kwargs: Additional data to pass to the subscribers

    Returns:
        int: Number of subscribers notified
    """
    return EventSystem.publish(event_name, book_id=book_id, **kwargs)


# Convenience function to publish chapter events
def publish_chapter_event(event_name: str, chapter_id: int, **kwargs) -> int:
    """
    Publish a chapter-related event

    Args:
        event_name: The name of the event from ChapterEvent class
        chapter_id: The ID of the chapter
        **kwargs: Additional data to pass to the subscribers

    Returns:
        int: Number of subscribers notified
    """
    return EventSystem.publish(event_name, chapter_id=chapter_id, **kwargs)


# Convenience function to publish user events
def publish_user_event(event_name: str, user_id: int, **kwargs) -> int:
    """
    Publish a user-related event

    Args:
        event_name: The name of the event from UserEvent class
        user_id: The ID of the user
        **kwargs: Additional data to pass to the subscribers

    Returns:
        int: Number of subscribers notified
    """
    return EventSystem.publish(event_name, user_id=user_id, **kwargs)
