import logging
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.crud.base import CRUDBase
from app.models.book import Book
from app.models.reading_list import ReadingList, ReadingListItem
from app.schemas.reading_list import (
    ReadingListCreate,
    ReadingListItemCreate,
    ReadingListItemUpdate,
    ReadingListUpdate,
)

logger = logging.getLogger(__name__)


class CRUDReadingList(CRUDBase[ReadingList, ReadingListCreate, ReadingListUpdate]):
    def get_by_user(
        self, db: Session, *, user_id: int, skip: int = 0, limit: int = 10000
    ) -> List[ReadingList]:
        """Get reading lists by user ID"""
        return (
            db.query(ReadingList)
            .filter(ReadingList.user_id == user_id, ReadingList.is_active == True)
            .order_by(ReadingList.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_by_user(self, db: Session, *, user_id: int) -> int:
        """Get total count of reading lists for a user."""
        return (
            db.query(ReadingList)
            .filter(ReadingList.user_id == user_id, ReadingList.is_active == True)
            .count()
        )

    def get_all_for_admin(
        self, db: Session, *, skip: int = 0, limit: int = 10000
    ) -> List[ReadingList]:
        """Get all reading lists for admin (including inactive ones)"""
        return (
            db.query(ReadingList)
            .order_by(ReadingList.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_all_for_admin(self, db: Session) -> int:
        """Get total count of all reading lists for admin."""
        return db.query(ReadingList).count()

    def get_with_items(self, db: Session, *, id: int) -> Optional[ReadingList]:
        """Get reading list with all items"""
        return (
            db.query(ReadingList)
            .options(joinedload(ReadingList.items).joinedload(ReadingListItem.book))
            .filter(ReadingList.id == id)
            .first()
        )

    def get_public(
        self, db: Session, *, skip: int = 0, limit: int = 10000
    ) -> List[ReadingList]:
        """Get public reading lists"""
        return (
            db.query(ReadingList)
            .filter(ReadingList.is_public == True, ReadingList.is_active == True)
            .order_by(ReadingList.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_public_lists(
        self, db: Session, *, skip: int = 0, limit: int = 100
    ) -> List[ReadingList]:
        """Get public reading lists for public access."""
        return self.get_public(db, skip=skip, limit=limit)

    def count_public_lists(self, db: Session) -> int:
        """Get total count of public reading lists."""
        return (
            db.query(ReadingList)
            .filter(ReadingList.is_public == True, ReadingList.is_active == True)
            .count()
        )

    def get_by_user_and_name(
        self, db: Session, *, user_id: int, name: str
    ) -> Optional[ReadingList]:
        """Get reading list by user and name"""
        return (
            db.query(ReadingList)
            .filter(
                ReadingList.user_id == user_id,
                ReadingList.name == name,
                ReadingList.is_active == True,
            )
            .first()
        )

    def create_user_list(
        self, db: Session, *, user_id: int, list_data: ReadingListCreate
    ) -> ReadingList:
        """Create a new reading list for a user"""
        reading_list = ReadingList(user_id=user_id, **list_data.model_dump())
        db.add(reading_list)
        db.commit()
        db.refresh(reading_list)
        return reading_list

    def soft_delete(
        self, db: Session, *, reading_list_id: int
    ) -> Optional[ReadingList]:
        """Soft delete a reading list by setting is_active to False"""
        reading_list = (
            db.query(ReadingList).filter(ReadingList.id == reading_list_id).first()
        )
        if reading_list:
            reading_list.is_active = False
            db.commit()
            db.refresh(reading_list)
        return reading_list


class CRUDReadingListItem(
    CRUDBase[ReadingListItem, ReadingListItemCreate, ReadingListItemUpdate]
):
    def get_by_list(
        self, db: Session, *, reading_list_id: int, skip: int = 0, limit: int = 10000
    ) -> List[ReadingListItem]:
        """Get reading list items by reading list ID"""
        return (
            db.query(ReadingListItem)
            .options(joinedload(ReadingListItem.book).joinedload(Book.author))
            .options(joinedload(ReadingListItem.book).joinedload(Book.category))
            .filter(ReadingListItem.reading_list_id == reading_list_id)
            .order_by(ReadingListItem.order_index)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_reading_list(
        self, db: Session, *, reading_list_id: int, skip: int = 0, limit: int = 10000
    ) -> List[ReadingListItem]:
        """Alias for get_by_list for compatibility"""
        return self.get_by_list(
            db, reading_list_id=reading_list_id, skip=skip, limit=limit
        )

    def get_by_reading_list_and_book(
        self, db: Session, *, reading_list_id: int, book_id: int
    ) -> Optional[ReadingListItem]:
        """Get reading list item by reading list and book"""
        return (
            db.query(ReadingListItem)
            .filter(
                ReadingListItem.reading_list_id == reading_list_id,
                ReadingListItem.book_id == book_id,
            )
            .first()
        )

    def get_by_list_and_book(
        self, db: Session, *, reading_list_id: int, book_id: int
    ) -> Optional[ReadingListItem]:
        """Get reading list item by list and book (legacy method)"""
        return self.get_by_reading_list_and_book(
            db, reading_list_id=reading_list_id, book_id=book_id
        )

    def add_book_to_list(
        self,
        db: Session,
        *,
        reading_list_id: int,
        book_id: int,
        notes: Optional[str] = None,
    ) -> ReadingListItem:
        """Add a book to a reading list"""
        # Check if item already exists
        existing_item = self.get_by_list_and_book(
            db, reading_list_id=reading_list_id, book_id=book_id
        )
        if existing_item:
            return existing_item

        # Get the next order index
        max_order = (
            db.query(ReadingListItem.order_index)
            .filter(ReadingListItem.reading_list_id == reading_list_id)
            .order_by(ReadingListItem.order_index.desc())
            .first()
        )
        next_order = (max_order[0] + 1) if max_order and max_order[0] else 1

        # Create new item
        reading_list_item = ReadingListItem(
            reading_list_id=reading_list_id,
            book_id=book_id,
            notes=notes,
            order_index=next_order,
        )
        db.add(reading_list_item)
        db.commit()
        db.refresh(reading_list_item)
        return reading_list_item

    def remove_book_from_list(
        self, db: Session, *, reading_list_id: int, book_id: int
    ) -> Optional[ReadingListItem]:
        """Remove a book from a reading list"""
        item = self.get_by_list_and_book(
            db, reading_list_id=reading_list_id, book_id=book_id
        )
        if item:
            db.delete(item)
            db.commit()
        return item

    def reorder_items(
        self, db: Session, *, reading_list_id: int, book_orders: List[tuple[int, int]]
    ) -> bool:
        """Reorder reading list items"""
        try:
            for book_id, new_order in book_orders:
                item = self.get_by_list_and_book(
                    db, reading_list_id=reading_list_id, book_id=book_id
                )
                if item:
                    item.order_index = new_order
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False

    def get_list_item_count(self, db: Session, *, reading_list_id: int) -> int:
        """Get count of items in a reading list"""
        return (
            db.query(ReadingListItem)
            .filter(ReadingListItem.reading_list_id == reading_list_id)
            .count()
        )


crud_reading_list = CRUDReadingList(ReadingList)
crud_reading_list_item = CRUDReadingListItem(ReadingListItem)
