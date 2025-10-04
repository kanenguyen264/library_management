import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.auth import get_password_hash, verify_password
from app.core.supabase_client import supabase_client
from app.crud.base import CRUDBase
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate

logger = logging.getLogger(__name__)


class CRUDUser(CRUDBase[User, UserCreate, UserUpdate]):
    def get_by_email(self, db: Session, *, email: str) -> Optional[User]:
        return db.query(User).filter(User.email == email).first()

    def get_by_username(self, db: Session, *, username: str) -> Optional[User]:
        return db.query(User).filter(User.username == username).first()

    def _cleanup_user_files(self, user: User) -> None:
        """
        Delete all files associated with a user from Supabase storage.
        """
        try:
            if not user.avatar_url:
                logger.info(f"No avatar file to delete for user: {user.username}")
                return

            logger.info(f"Deleting avatar file for user: {user.username}")

            try:
                success = supabase_client.delete_file(user.avatar_url)
                if success:
                    logger.info(f"Avatar file deleted successfully: {user.avatar_url}")
                else:
                    logger.warning(f"Failed to delete avatar file: {user.avatar_url}")
            except Exception as file_error:
                logger.error(
                    f"Error deleting avatar file {user.avatar_url}: {str(file_error)}"
                )

        except Exception as e:
            logger.error(f"Error cleaning up user files for {user.username}: {str(e)}")

    def _cleanup_old_files_on_update(
        self, old_user: User, update_data: Dict[str, Any]
    ) -> None:
        """
        Delete old avatar when it's being replaced with new one or removed.
        """
        try:
            logger.info(f"Checking avatar changes for user: {old_user.username}")

            # Check avatar_url update
            if "avatar_url" in update_data:
                new_avatar_url = update_data["avatar_url"] or ""  # Handle None
                old_avatar_url = old_user.avatar_url or ""  # Handle None

                # If URLs are different AND old URL exists, delete old file
                if new_avatar_url != old_avatar_url and old_avatar_url:
                    logger.info(
                        f"Avatar URL changed, deleting old avatar: {old_avatar_url}"
                    )
                    try:
                        success = supabase_client.delete_file(old_avatar_url)
                        if success:
                            logger.info(
                                f"Successfully deleted old avatar: {old_avatar_url}"
                            )
                        else:
                            logger.warning(
                                f"Failed to delete old avatar: {old_avatar_url}"
                            )
                    except Exception as e:
                        logger.error(
                            f"Error deleting old avatar {old_avatar_url}: {str(e)}"
                        )

        except Exception as e:
            logger.error(
                f"Error cleaning up old files for {old_user.username}: {str(e)}"
            )

    def create(self, db: Session, *, obj_in: UserCreate) -> User:
        db_obj = User(
            email=obj_in.email,
            username=obj_in.username,
            full_name=obj_in.full_name,
            hashed_password=get_password_hash(obj_in.password),
            is_active=obj_in.is_active,
            is_admin=obj_in.is_admin,
            avatar_url=obj_in.avatar_url,
            bio=obj_in.bio,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(
        self, db: Session, *, db_obj: User, obj_in: Union[UserUpdate, Dict[str, Any]]
    ) -> User:
        """
        Update a user and cleanup old avatar when replaced.
        """
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)

        # Convert empty strings to None for optional fields
        optional_string_fields = ["avatar_url", "bio"]
        for field in optional_string_fields:
            if field in update_data and update_data[field] == "":
                update_data[field] = None

        logger.info(f"Updating user: {db_obj.username} (ID: {db_obj.id})")

        # Cleanup old files that are being replaced
        self._cleanup_old_files_on_update(db_obj, update_data)

        if "password" in update_data:
            hashed_password = get_password_hash(update_data["password"])
            del update_data["password"]
            update_data["hashed_password"] = hashed_password

        try:
            updated_user = super().update(db, db_obj=db_obj, obj_in=update_data)
            logger.info(f"User updated successfully: {updated_user.username}")
            return updated_user
        except Exception as e:
            logger.error(f"Error updating user {db_obj.id}: {str(e)}")
            raise e

    def remove(self, db: Session, *, id: int) -> User:
        """
        Delete a user and cleanup all associated files.
        """
        from app.models.reading_progress import ReadingProgress

        # Get the user first to access file URLs
        user = self.get(db, id=id)
        if not user:
            logger.warning(f"User with ID {id} not found for deletion")
            return None

        logger.info(f"Deleting user: {user.username} (ID: {id})")

        try:
            # Check if there are reading progress records by this user
            progress_count = (
                db.query(ReadingProgress).filter(ReadingProgress.user_id == id).count()
            )

            if progress_count > 0:
                logger.warning(
                    f"Cannot delete user {user.username}: {progress_count} reading progress records are associated with this user"
                )
                raise ValueError(
                    f"Cannot delete user. There are {progress_count} reading progress records associated with this user. Please delete or reassign the records first."
                )

            # Cleanup all files before deleting the record
            self._cleanup_user_files(user)

            # Delete the user record
            db.delete(user)
            db.commit()

            logger.info(f"User deleted successfully: {user.username}")
            return user
        except ValueError:
            # Re-raise constraint errors without rollback
            raise
        except Exception as e:
            # Rollback the transaction if deletion fails
            db.rollback()
            logger.error(f"Error deleting user {id}: {str(e)}")
            raise e

    def authenticate(self, db: Session, *, email: str, password: str) -> Optional[User]:
        user = self.get_by_email(db, email=email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    def is_active(self, user: User) -> bool:
        return user.is_active

    def is_admin(self, user: User) -> bool:
        return user.is_admin

    def get_multi_with_filters(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
        filters: Dict[str, Any] = None,
    ) -> List[User]:
        """
        Get users with search and filter capabilities.
        """
        query = db.query(self.model)

        if filters:
            conditions = []

            # Search across username, email, and full_name
            if "search" in filters and filters["search"]:
                search_term = f"%{filters['search']}%"
                search_conditions = [
                    User.username.ilike(search_term),
                    User.email.ilike(search_term),
                    User.full_name.ilike(search_term),
                ]
                conditions.append(or_(*search_conditions))

            # Filter by active status
            if "is_active" in filters and filters["is_active"] is not None:
                conditions.append(User.is_active == filters["is_active"])

            # Filter by admin status
            if "is_admin" in filters and filters["is_admin"] is not None:
                conditions.append(User.is_admin == filters["is_admin"])

            # Filter by creation date range
            if "created_from" in filters and filters["created_from"]:
                conditions.append(User.created_at >= filters["created_from"])

            if "created_to" in filters and filters["created_to"]:
                conditions.append(User.created_at <= filters["created_to"])

            # Apply all conditions
            if conditions:
                query = query.filter(and_(*conditions))

        return query.order_by(User.created_at.desc()).offset(skip).limit(limit).all()

    def count_with_filters(self, db: Session, *, filters: Dict[str, Any] = None) -> int:
        """
        Count users with search and filter capabilities.
        """
        query = db.query(self.model)

        if filters:
            conditions = []

            # Search across username, email, and full_name
            if "search" in filters and filters["search"]:
                search_term = f"%{filters['search']}%"
                search_conditions = [
                    User.username.ilike(search_term),
                    User.email.ilike(search_term),
                    User.full_name.ilike(search_term),
                ]
                conditions.append(or_(*search_conditions))

            # Filter by active status
            if "is_active" in filters and filters["is_active"] is not None:
                conditions.append(User.is_active == filters["is_active"])

            # Filter by admin status
            if "is_admin" in filters and filters["is_admin"] is not None:
                conditions.append(User.is_admin == filters["is_admin"])

            # Filter by creation date range
            if "created_from" in filters and filters["created_from"]:
                conditions.append(User.created_at >= filters["created_from"])

            if "created_to" in filters and filters["created_to"]:
                conditions.append(User.created_at <= filters["created_to"])

            # Apply all conditions
            if conditions:
                query = query.filter(and_(*conditions))

        return query.count()


crud_user = CRUDUser(User)
