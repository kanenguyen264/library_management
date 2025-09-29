from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
import logging

from app.user_site.schemas.user import UserPreference
from app.user_site.repositories.preference_repo import PreferenceRepository
from app.user_site.repositories.user_repo import UserRepository
from app.core.exceptions import NotFoundException, ForbiddenException
from app.cache.decorators import cached, invalidate_cache
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

# Logger for preference service
logger = logging.getLogger(__name__)


async def get_all_preferences(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None,
    admin_id: Optional[int] = None,
) -> List[UserPreference]:
    """
    Get list of user preferences with optional filtering.

    Args:
        db: Database session
        skip: Number of records to skip
        limit: Maximum number of records to return
        user_id: Filter by user ID
        admin_id: ID of admin performing the action

    Returns:
        List of user preferences
    """
    try:
        repo = PreferenceRepository(db)

        if user_id:
            # If user_id is provided, get only that user's preferences
            preferences = await repo.get_user_preferences(user_id)
        else:
            # Currently repository may not support listing all preferences
            # This would need to be implemented in the repository
            logger.warning("Listing all preferences is not fully supported")
            preferences = await repo.list(skip=skip, limit=limit)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="PREFERENCES",
                        entity_id=0,
                        description="Viewed preferences list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "user_id": user_id,
                            "results_count": len(preferences),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return preferences
    except Exception as e:
        logger.error(f"Error retrieving preferences: {str(e)}")
        raise


@cached(key_prefix="admin_preference", ttl=300)
async def get_preference_by_id(
    db: Session, preference_id: int, admin_id: Optional[int] = None
) -> UserPreference:
    """
    Get preference by ID.

    Args:
        db: Database session
        preference_id: Preference ID
        admin_id: ID of admin performing the action

    Returns:
        Preference details

    Raises:
        NotFoundException: If preference not found
    """
    try:
        repo = PreferenceRepository(db)
        preference = await repo.get_by_id(preference_id)

        if not preference:
            logger.warning(f"Preference with ID {preference_id} not found")
            raise NotFoundException(
                detail=f"Preference with ID {preference_id} not found"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="PREFERENCE",
                        entity_id=preference_id,
                        description=f"Viewed preference details for key: {preference.key}",
                        metadata={
                            "user_id": preference.user_id,
                            "key": preference.key,
                            "value": preference.value,
                            "data_type": preference.data_type,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return preference
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving preference: {str(e)}")
        raise


@cached(key_prefix="admin_user_preferences", ttl=300)
async def get_user_preferences(
    db: Session, user_id: int, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get all preferences for a specific user.

    Args:
        db: Database session
        user_id: User ID
        admin_id: ID of admin performing the action

    Returns:
        Dictionary of user preferences

    Raises:
        NotFoundException: If user not found
    """
    try:
        # Check if user exists
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(detail=f"User with ID {user_id} not found")

        repo = PreferenceRepository(db)
        preferences = await repo.get_user_preferences(user_id)

        # Convert to dictionary format for easier consumption
        result = {}
        for pref in preferences:
            result[pref.key] = {
                "id": pref.id,
                "value": pref.value,
                "data_type": pref.data_type,
                "created_at": pref.created_at,
                "updated_at": pref.updated_at,
            }

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="USER_PREFERENCES",
                        entity_id=user_id,
                        description=f"Viewed all preferences for user {user_id}",
                        metadata={
                            "user_id": user_id,
                            "username": (
                                user.username if hasattr(user, "username") else None
                            ),
                            "preference_count": len(preferences),
                            "preference_keys": list(result.keys()),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return result
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user preferences: {str(e)}")
        raise


async def get_user_preference(
    db: Session, user_id: int, key: str, admin_id: Optional[int] = None
) -> Optional[UserPreference]:
    """
    Get a specific preference for a user.

    Args:
        db: Database session
        user_id: User ID
        key: Preference key
        admin_id: ID of admin performing the action

    Returns:
        User preference or None if not found

    Raises:
        NotFoundException: If user not found
    """
    try:
        # Check if user exists
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(detail=f"User with ID {user_id} not found")

        repo = PreferenceRepository(db)
        preference = await repo.get_user_preference(user_id, key)

        # Log admin activity
        if admin_id and preference:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="USER_PREFERENCE",
                        entity_id=preference.id,
                        description=f"Viewed preference '{key}' for user {user_id}",
                        metadata={
                            "user_id": user_id,
                            "username": (
                                user.username if hasattr(user, "username") else None
                            ),
                            "key": key,
                            "value": preference.value if preference else None,
                            "data_type": preference.data_type if preference else None,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return preference
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user preference: {str(e)}")
        raise


async def create_preference(
    db: Session,
    user_id: int,
    key: str,
    value: Any,
    data_type: str = "string",
    admin_id: Optional[int] = None,
) -> UserPreference:
    """
    Create a new preference for a user.

    Args:
        db: Database session
        user_id: User ID
        key: Preference key
        value: Preference value
        data_type: Data type of the preference value
        admin_id: ID of admin performing the action

    Returns:
        Created preference

    Raises:
        NotFoundException: If user not found
        ForbiddenException: If preference already exists
    """
    try:
        # Check if user exists
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(detail=f"User with ID {user_id} not found")

        # Check if preference already exists
        repo = PreferenceRepository(db)
        existing = await repo.get_user_preference(user_id, key)

        if existing:
            logger.warning(f"Preference {key} already exists for user {user_id}")
            raise ForbiddenException(
                detail=f"Preference {key} already exists for user {user_id}"
            )

        # Create preference
        preference_data = {
            "user_id": user_id,
            "key": key,
            "value": value,
            "data_type": data_type,
        }

        preference = await repo.create(preference_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="PREFERENCE",
                        entity_id=preference.id,
                        description=f"Created preference '{key}' for user {user_id}",
                        metadata={
                            "user_id": user_id,
                            "username": (
                                user.username if hasattr(user, "username") else None
                            ),
                            "key": key,
                            "value": value,
                            "data_type": data_type,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove cache
        invalidate_cache(f"admin_user_preferences:{user_id}")

        logger.info(f"Created preference {key} for user {user_id}")
        return preference
    except NotFoundException:
        raise
    except ForbiddenException:
        raise
    except Exception as e:
        logger.error(f"Error creating preference: {str(e)}")
        raise


async def update_preference(
    db: Session,
    user_id: int,
    key: str,
    value: Any,
    data_type: Optional[str] = None,
    admin_id: Optional[int] = None,
) -> UserPreference:
    """
    Update a user preference or create if it doesn't exist.

    Args:
        db: Database session
        user_id: User ID
        key: Preference key
        value: New preference value
        data_type: Data type of the preference value
        admin_id: ID of admin performing the action

    Returns:
        Updated preference

    Raises:
        NotFoundException: If user not found
    """
    try:
        # Check if user exists
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(detail=f"User with ID {user_id} not found")

        repo = PreferenceRepository(db)

        # Try to get existing preference
        existing = await repo.get_user_preference(user_id, key)

        old_value = None
        old_data_type = None
        action_type = "UPDATE"

        if existing:
            # Update existing preference
            old_value = existing.value
            old_data_type = existing.data_type

            update_data = {"value": value}
            if data_type:
                update_data["data_type"] = data_type

            updated = await repo.update(existing.id, update_data)

            # Remove cache
            invalidate_cache(f"admin_preference:{existing.id}")
            invalidate_cache(f"admin_user_preferences:{user_id}")

            logger.info(f"Updated preference {key} for user {user_id}")
            result = updated
        else:
            # Create new preference
            action_type = "CREATE"
            preference_data = {
                "user_id": user_id,
                "key": key,
                "value": value,
                "data_type": data_type or "string",
            }

            created = await repo.create(preference_data)

            # Remove cache
            invalidate_cache(f"admin_user_preferences:{user_id}")

            logger.info(f"Created preference {key} for user {user_id}")
            result = created

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type=action_type,
                        entity_type="PREFERENCE",
                        entity_id=result.id,
                        description=f"{action_type.capitalize()}d preference '{key}' for user {user_id}",
                        metadata={
                            "user_id": user_id,
                            "username": (
                                user.username if hasattr(user, "username") else None
                            ),
                            "key": key,
                            "old_value": old_value,
                            "new_value": value,
                            "old_data_type": old_data_type,
                            "new_data_type": data_type
                            or (existing.data_type if existing else "string"),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return result
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error updating preference: {str(e)}")
        raise


async def delete_preference(
    db: Session, user_id: int, key: str, admin_id: Optional[int] = None
) -> bool:
    """
    Delete a user preference.

    Args:
        db: Database session
        user_id: User ID
        key: Preference key
        admin_id: ID of admin performing the action

    Returns:
        True if deleted, False if not found

    Raises:
        NotFoundException: If user not found
    """
    try:
        # Check if user exists
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(detail=f"User with ID {user_id} not found")

        repo = PreferenceRepository(db)

        # Try to get existing preference
        existing = await repo.get_user_preference(user_id, key)

        if existing:
            # Delete preference
            await repo.delete(existing.id)

            # Log admin activity
            if admin_id:
                try:
                    await create_admin_activity_log(
                        db,
                        AdminActivityLogCreate(
                            admin_id=admin_id,
                            activity_type="DELETE",
                            entity_type="PREFERENCE",
                            entity_id=existing.id,
                            description=f"Deleted preference '{key}' for user {user_id}",
                            metadata={
                                "user_id": user_id,
                                "username": (
                                    user.username if hasattr(user, "username") else None
                                ),
                                "key": key,
                                "value": existing.value,
                                "data_type": existing.data_type,
                            },
                        ),
                    )
                except Exception as e:
                    logger.error(f"Failed to log admin activity: {str(e)}")

            # Remove cache
            invalidate_cache(f"admin_preference:{existing.id}")
            invalidate_cache(f"admin_user_preferences:{user_id}")

            logger.info(f"Deleted preference {key} for user {user_id}")
            return True
        else:
            # Preference doesn't exist
            logger.warning(f"Preference {key} not found for user {user_id}")
            return False
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting preference: {str(e)}")
        raise


async def delete_all_user_preferences(
    db: Session, user_id: int, admin_id: Optional[int] = None
) -> int:
    """
    Delete all preferences for a user.

    Args:
        db: Database session
        user_id: User ID
        admin_id: ID of admin performing the action

    Returns:
        Number of deleted preferences

    Raises:
        NotFoundException: If user not found
    """
    try:
        # Check if user exists
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(detail=f"User with ID {user_id} not found")

        # Get list of preferences for logging
        repo = PreferenceRepository(db)
        preferences = await repo.get_user_preferences(user_id)
        preference_keys = [p.key for p in preferences]

        count = await repo.delete_user_preferences(user_id)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="USER_PREFERENCES",
                        entity_id=user_id,
                        description=f"Deleted all preferences for user {user_id}",
                        metadata={
                            "user_id": user_id,
                            "username": (
                                user.username if hasattr(user, "username") else None
                            ),
                            "count": count,
                            "deleted_keys": preference_keys,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove cache
        invalidate_cache(f"admin_user_preferences:{user_id}")

        logger.info(f"Deleted {count} preferences for user {user_id}")
        return count
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user preferences: {str(e)}")
        raise


async def set_theme_preference(
    db: Session, user_id: int, theme: str, admin_id: Optional[int] = None
) -> UserPreference:
    """
    Set theme preference for a user.

    Args:
        db: Database session
        user_id: User ID
        theme: Theme name (light/dark/system)
        admin_id: ID of admin performing the action

    Returns:
        Updated preference

    Raises:
        NotFoundException: If user not found
        ForbiddenException: If invalid theme
    """
    try:
        # Validate theme
        valid_themes = ["light", "dark", "system"]
        if theme not in valid_themes:
            logger.warning(f"Invalid theme: {theme}")
            raise ForbiddenException(
                detail=f"Invalid theme. Must be one of: {', '.join(valid_themes)}"
            )

        # Log specific action before updating
        if admin_id:
            # Check if user exists
            user_repo = UserRepository(db)
            user = await user_repo.get_by_id(user_id)

            if user:
                try:
                    await create_admin_activity_log(
                        db,
                        AdminActivityLogCreate(
                            admin_id=admin_id,
                            activity_type="UPDATE",
                            entity_type="THEME_PREFERENCE",
                            entity_id=user_id,
                            description=f"Set theme preference to '{theme}' for user {user_id}",
                            metadata={
                                "user_id": user_id,
                                "username": (
                                    user.username if hasattr(user, "username") else None
                                ),
                                "theme": theme,
                            },
                        ),
                    )
                except Exception as e:
                    logger.error(f"Failed to log admin activity: {str(e)}")

        return await update_preference(db, user_id, "theme", theme, "string")
    except NotFoundException:
        raise
    except ForbiddenException:
        raise
    except Exception as e:
        logger.error(f"Error setting theme preference: {str(e)}")
        raise


async def set_language_preference(
    db: Session, user_id: int, language: str, admin_id: Optional[int] = None
) -> UserPreference:
    """
    Set language preference for a user.

    Args:
        db: Database session
        user_id: User ID
        language: Language code
        admin_id: ID of admin performing the action

    Returns:
        Updated preference

    Raises:
        NotFoundException: If user not found
    """
    try:
        # Log specific action before updating
        if admin_id:
            # Check if user exists
            user_repo = UserRepository(db)
            user = await user_repo.get_by_id(user_id)

            if user:
                try:
                    await create_admin_activity_log(
                        db,
                        AdminActivityLogCreate(
                            admin_id=admin_id,
                            activity_type="UPDATE",
                            entity_type="LANGUAGE_PREFERENCE",
                            entity_id=user_id,
                            description=f"Set language preference to '{language}' for user {user_id}",
                            metadata={
                                "user_id": user_id,
                                "username": (
                                    user.username if hasattr(user, "username") else None
                                ),
                                "language": language,
                            },
                        ),
                    )
                except Exception as e:
                    logger.error(f"Failed to log admin activity: {str(e)}")

        # Here you could validate language codes if needed
        return await update_preference(db, user_id, "language", language, "string")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error setting language preference: {str(e)}")
        raise


async def set_notification_preferences(
    db: Session,
    user_id: int,
    email_notifications: bool,
    push_notifications: bool,
    marketing_emails: bool,
    admin_id: Optional[int] = None,
) -> Dict[str, UserPreference]:
    """
    Set notification preferences for a user.

    Args:
        db: Database session
        user_id: User ID
        email_notifications: Enable email notifications
        push_notifications: Enable push notifications
        marketing_emails: Enable marketing emails
        admin_id: ID of admin performing the action

    Returns:
        Dictionary of updated preferences

    Raises:
        NotFoundException: If user not found
    """
    try:
        # Log specific action before updating
        if admin_id:
            # Check if user exists
            user_repo = UserRepository(db)
            user = await user_repo.get_by_id(user_id)

            if user:
                try:
                    await create_admin_activity_log(
                        db,
                        AdminActivityLogCreate(
                            admin_id=admin_id,
                            activity_type="UPDATE",
                            entity_type="NOTIFICATION_PREFERENCES",
                            entity_id=user_id,
                            description=f"Updated notification preferences for user {user_id}",
                            metadata={
                                "user_id": user_id,
                                "username": (
                                    user.username if hasattr(user, "username") else None
                                ),
                                "email_notifications": email_notifications,
                                "push_notifications": push_notifications,
                                "marketing_emails": marketing_emails,
                            },
                        ),
                    )
                except Exception as e:
                    logger.error(f"Failed to log admin activity: {str(e)}")

        # Update each preference
        email_pref = await update_preference(
            db, user_id, "email_notifications", email_notifications, "boolean"
        )
        push_pref = await update_preference(
            db, user_id, "push_notifications", push_notifications, "boolean"
        )
        marketing_pref = await update_preference(
            db, user_id, "marketing_emails", marketing_emails, "boolean"
        )

        return {
            "email_notifications": email_pref,
            "push_notifications": push_pref,
            "marketing_emails": marketing_pref,
        }
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error setting notification preferences: {str(e)}")
        raise


async def get_default_preference_settings() -> Dict[str, Any]:
    """
    Get default preference settings for new users.

    Returns:
        Dictionary of default preference settings
    """
    return {
        "theme": "system",
        "language": "en",
        "email_notifications": True,
        "push_notifications": True,
        "marketing_emails": False,
        "font_size": "medium",
        "reading_mode": "continuous",
    }


async def initialize_user_preferences(
    db: Session, user_id: int, admin_id: Optional[int] = None
) -> Dict[str, UserPreference]:
    """
    Initialize default preferences for a new user.

    Args:
        db: Database session
        user_id: User ID
        admin_id: ID of admin performing the action

    Returns:
        Dictionary of created preferences

    Raises:
        NotFoundException: If user not found
    """
    try:
        # Check if user exists
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(detail=f"User with ID {user_id} not found")

        # Get default preferences
        defaults = await get_default_preference_settings()

        # Create preferences
        result = {}
        for key, value in defaults.items():
            data_type = "boolean" if isinstance(value, bool) else "string"
            try:
                pref = await create_preference(db, user_id, key, value, data_type)
                result[key] = pref
            except ForbiddenException:
                # Preference already exists, skip
                pass

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="USER_PREFERENCES",
                        entity_id=user_id,
                        description=f"Initialized default preferences for user {user_id}",
                        metadata={
                            "user_id": user_id,
                            "username": (
                                user.username if hasattr(user, "username") else None
                            ),
                            "created_preferences": list(result.keys()),
                            "default_values": defaults,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Initialized preferences for user {user_id}")
        return result
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error initializing user preferences: {str(e)}")
        raise


@cached(key_prefix="admin_preference_statistics", ttl=3600)
async def get_preference_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get statistics about user preferences.

    Args:
        db: Database session
        admin_id: ID of admin performing the action

    Returns:
        Dictionary of preference statistics
    """
    try:
        repo = PreferenceRepository(db)

        # This assumes repository has methods to get these statistics
        # You may need to implement these in the repository
        theme_distribution = await repo.get_preference_distribution("theme")
        language_distribution = await repo.get_preference_distribution("language")

        # Count users with email notifications enabled
        email_notifications = await repo.count_with_value("email_notifications", True)

        # Count users with push notifications enabled
        push_notifications = await repo.count_with_value("push_notifications", True)

        # Count users with marketing emails enabled
        marketing_emails = await repo.count_with_value("marketing_emails", True)

        stats = {
            "theme_distribution": theme_distribution,
            "language_distribution": language_distribution,
            "email_notifications_enabled": email_notifications,
            "push_notifications_enabled": push_notifications,
            "marketing_emails_enabled": marketing_emails,
        }

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="PREFERENCE_STATISTICS",
                        entity_id=0,
                        description="Viewed preference system statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Error retrieving preference statistics: {str(e)}")
        raise
