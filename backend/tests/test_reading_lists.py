from app.crud.reading_list import crud_reading_list, crud_reading_list_item
from app.crud.reading_progress import crud_reading_progress
from app.schemas.reading_list import ReadingListCreate
from app.schemas.reading_progress import ReadingProgressCreate
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


class TestReadingLists:
    """Test cases for reading lists functionality"""

    def test_create_reading_list(self, client: TestClient, auth_headers: dict):
        """Test creating a reading list"""
        reading_list_data = {
            "name": "My Test List",
            "description": "A test reading list",
            "is_public": False,
            "is_active": True
        }
        response = client.post(
            "/api/v1/reading-lists/",
            headers=auth_headers,
            json=reading_list_data,
        )
        assert response.status_code == 201
        response_data = response.json()
        data = response_data["data"]  # Extract from wrapped response
        assert data["name"] == reading_list_data["name"]
        assert data["description"] == reading_list_data["description"]
        assert data["is_public"] == reading_list_data["is_public"]
        assert "id" in data
        assert "created_at" in data

    def test_create_reading_list_duplicate_name(self, client: TestClient, db_session: Session, auth_headers: dict, test_user):
        """Test creating a reading list with duplicate name fails"""
        # Create first reading list
        reading_list_data = ReadingListCreate(
            user_id=test_user.id,
            name="My Test List",
            description="A test reading list",
            is_public=False,
            is_active=True
        )
        crud_reading_list.create(db_session, obj_in=reading_list_data)
        
        # Try to create another with same name
        duplicate_data = {
            "name": "My Test List",
            "description": "Another test reading list",
            "is_public": False,
            "is_active": True
        }
        response = client.post(
            "/api/v1/reading-lists/",
            headers=auth_headers,
            json=duplicate_data,
        )
        assert response.status_code == 400
        assert "already have a reading list with this name" in response.json()["detail"]

    def test_get_my_reading_lists(self, client: TestClient, db_session: Session, auth_headers: dict, test_user):
        """Test getting current user's reading lists"""
        # Create reading lists
        for i in range(3):
            reading_list_data = ReadingListCreate(
                user_id=test_user.id,
                name=f"Test List {i}",
                description=f"Description {i}",
                is_public=i % 2 == 0,
                is_active=True
            )
            crud_reading_list.create(db_session, obj_in=reading_list_data)
        
        response = client.get("/api/v1/reading-lists/", headers=auth_headers)
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]  # Extract from wrapped response
        assert len(data) == 3

    def test_get_reading_list_with_items(self, client: TestClient, db_session: Session, auth_headers: dict, test_user, test_book):
        """Test getting a reading list with its items"""
        # Create reading list
        reading_list_data = ReadingListCreate(
            user_id=test_user.id,
            name="Test List with Items",
            description="Test description",
            is_public=False,
            is_active=True
        )
        reading_list = crud_reading_list.create(db_session, obj_in=reading_list_data)
        
        # Add a book to the list
        crud_reading_list_item.add_book_to_list(
            db_session, reading_list_id=reading_list.id, book_id=test_book.id
        )
        
        response = client.get(f"/api/v1/reading-lists/{reading_list.id}", headers=auth_headers)
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]  # Extract from wrapped response
        assert data["name"] == "Test List with Items"
        assert len(data["items"]) == 1
        assert data["items"][0]["book"]["id"] == test_book.id

    def test_get_reading_list_not_found(self, client: TestClient, auth_headers: dict):
        """Test getting non-existent reading list"""
        response = client.get("/api/v1/reading-lists/999", headers=auth_headers)
        assert response.status_code == 404

    def test_get_reading_list_no_permission(self, client: TestClient, db_session: Session, auth_headers: dict, test_user_2):
        """Test getting someone else's private reading list fails"""
        # Create a private reading list for test_user_2
        reading_list_data = ReadingListCreate(
            user_id=test_user_2.id,
            name="Private List",
            description="Private description",
            is_public=False,
            is_active=True
        )
        reading_list = crud_reading_list.create(db_session, obj_in=reading_list_data)
        
        # Try to access with different user's auth
        response = client.get(f"/api/v1/reading-lists/{reading_list.id}", headers=auth_headers)
        assert response.status_code == 403

    def test_get_public_reading_list(self, client: TestClient, db_session: Session, auth_headers: dict, test_user_2):
        """Test getting someone else's public reading list succeeds"""
        # Create a public reading list for test_user_2
        reading_list_data = ReadingListCreate(
            user_id=test_user_2.id,
            name="Public List",
            description="Public description",
            is_public=True,
            is_active=True
        )
        reading_list = crud_reading_list.create(db_session, obj_in=reading_list_data)
        
        # Should be able to access public list
        response = client.get(f"/api/v1/reading-lists/{reading_list.id}", headers=auth_headers)
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]  # Extract from wrapped response
        assert data["name"] == "Public List"

    def test_update_reading_list(self, client: TestClient, db_session: Session, auth_headers: dict, test_user):
        """Test updating a reading list"""
        # Create reading list
        reading_list_data = ReadingListCreate(
            user_id=test_user.id,
            name="Original Name",
            description="Original description",
            is_public=False,
            is_active=True
        )
        reading_list = crud_reading_list.create(db_session, obj_in=reading_list_data)
        
        # Update the reading list
        update_data = {
            "name": "Updated Name",
            "description": "Updated description",
            "is_public": True
        }
        response = client.put(
            f"/api/v1/reading-lists/{reading_list.id}",
            headers=auth_headers,
            json=update_data,
        )
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]  # Extract from wrapped response
        assert data["name"] == "Updated Name"
        assert data["description"] == "Updated description"
        assert data["is_public"] == True

    def test_update_reading_list_no_permission(self, client: TestClient, db_session: Session, auth_headers: dict, test_user_2):
        """Test updating someone else's reading list fails"""
        # Create reading list for test_user_2
        reading_list_data = ReadingListCreate(
            user_id=test_user_2.id,
            name="Other User's List",
            description="Description",
            is_public=False,
            is_active=True
        )
        reading_list = crud_reading_list.create(db_session, obj_in=reading_list_data)
        
        # Try to update with different user's auth
        update_data = {"name": "Hacked Name"}
        response = client.put(
            f"/api/v1/reading-lists/{reading_list.id}",
            headers=auth_headers,
            json=update_data,
        )
        assert response.status_code == 403

    def test_delete_reading_list(self, client: TestClient, db_session: Session, auth_headers: dict, test_user):
        """Test deleting a reading list"""
        # Create reading list
        reading_list_data = ReadingListCreate(
            user_id=test_user.id,
            name="To Be Deleted",
            description="Will be deleted",
            is_public=False,
            is_active=True
        )
        reading_list = crud_reading_list.create(db_session, obj_in=reading_list_data)
        
        response = client.delete(f"/api/v1/reading-lists/{reading_list.id}", headers=auth_headers)
        assert response.status_code == 200

    def test_add_book_to_reading_list(self, client: TestClient, db_session: Session, auth_headers: dict, test_user, test_book):
        """Test adding a book to a reading list"""
        # Create reading progress first (required by business logic)
        progress_data = ReadingProgressCreate(
            user_id=test_user.id,
            book_id=test_book.id,
            current_page=1,
            total_pages=test_book.pages,
            status="reading"
        )
        crud_reading_progress.create(db_session, obj_in=progress_data)
        
        # Create reading list
        reading_list_data = ReadingListCreate(
            user_id=test_user.id,
            name="Book List",
            description="List for books",
            is_public=False,
            is_active=True
        )
        reading_list = crud_reading_list.create(db_session, obj_in=reading_list_data)
        
        response = client.post(
            f"/api/v1/reading-lists/{reading_list.id}/books/{test_book.id}",
            headers=auth_headers,
        )
        assert response.status_code == 201
        response_data = response.json()
        data = response_data["data"]  # Extract from wrapped response
        assert data["book_id"] == test_book.id

    def test_add_book_to_reading_list_with_notes(self, client: TestClient, db_session: Session, auth_headers: dict, test_user, test_book):
        """Test adding a book to reading list with notes"""
        # Create reading progress first (required by business logic)
        progress_data = ReadingProgressCreate(
            user_id=test_user.id,
            book_id=test_book.id,
            current_page=1,
            total_pages=test_book.pages,
            status="reading"
        )
        crud_reading_progress.create(db_session, obj_in=progress_data)
        
        # Create reading list
        reading_list_data = ReadingListCreate(
            user_id=test_user.id,
            name="Book List",
            description="List for books",
            is_public=False,
            is_active=True
        )
        reading_list = crud_reading_list.create(db_session, obj_in=reading_list_data)
        
        response = client.post(
            f"/api/v1/reading-lists/{reading_list.id}/books/{test_book.id}?notes=Great book!",
            headers=auth_headers,
        )
        assert response.status_code == 201
        response_data = response.json()
        data = response_data["data"]  # Extract from wrapped response
        assert data["book_id"] == test_book.id
        assert data["notes"] == "Great book!"

    def test_add_book_nonexistent_book(self, client: TestClient, db_session: Session, auth_headers: dict, test_user):
        """Test adding non-existent book to reading list"""
        # Create reading list
        reading_list_data = ReadingListCreate(
            user_id=test_user.id,
            name="Book List",
            description="List for books",
            is_public=False,
            is_active=True
        )
        reading_list = crud_reading_list.create(db_session, obj_in=reading_list_data)
        
        response = client.post(
            f"/api/v1/reading-lists/{reading_list.id}/books/999",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_remove_book_from_reading_list(self, client: TestClient, db_session: Session, auth_headers: dict, test_user, test_book):
        """Test removing a book from reading list"""
        # Create reading list and add book
        reading_list_data = ReadingListCreate(
            user_id=test_user.id,
            name="Book List",
            description="List for books",
            is_public=False,
            is_active=True
        )
        reading_list = crud_reading_list.create(db_session, obj_in=reading_list_data)
        crud_reading_list_item.add_book_to_list(
            db_session, reading_list_id=reading_list.id, book_id=test_book.id
        )
        
        response = client.delete(
            f"/api/v1/reading-lists/{reading_list.id}/books/{test_book.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        response_data = response.json()
        # For delete responses, we expect success message
        assert response_data["success"] == True

    def test_reorder_reading_list_items(self, client: TestClient, db_session: Session, auth_headers: dict, test_user, test_book, test_book_2):
        """Test reordering items in reading list"""
        # Create reading list and add books
        reading_list_data = ReadingListCreate(
            user_id=test_user.id,
            name="Book List",
            description="List for books",
            is_public=False,
            is_active=True
        )
        reading_list = crud_reading_list.create(db_session, obj_in=reading_list_data)
        
        # Add books
        item1 = crud_reading_list_item.add_book_to_list(
            db_session, reading_list_id=reading_list.id, book_id=test_book.id
        )
        item2 = crud_reading_list_item.add_book_to_list(
            db_session, reading_list_id=reading_list.id, book_id=test_book_2.id
        )
        
        # Reorder items
        reorder_data = [
            {"book_id": test_book_2.id, "order": 1},
            {"book_id": test_book.id, "order": 2}
        ]
        response = client.put(
            f"/api/v1/reading-lists/{reading_list.id}/reorder",
            headers=auth_headers,
            json=reorder_data,
        )
        assert response.status_code == 200
        response_data = response.json()
        # For update responses, we expect data with the updated reading list
        data = response_data["data"]
        assert data["id"] == reading_list.id

    def test_get_public_reading_lists(self, client: TestClient, db_session: Session, test_user):
        """Test getting public reading lists"""
        # Create public reading lists
        for i in range(3):
            reading_list_data = ReadingListCreate(
                user_id=test_user.id,
                name=f"Public List {i}",
                description=f"Public description {i}",
                is_public=True,
                is_active=True
            )
            crud_reading_list.create(db_session, obj_in=reading_list_data)
        
        # Create private reading list (should not appear)
        private_data = ReadingListCreate(
            user_id=test_user.id,
            name="Private List",
            description="Private description",
            is_public=False,
            is_active=True
        )
        crud_reading_list.create(db_session, obj_in=private_data)
        
        response = client.get("/api/v1/reading-lists/public/lists")
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]  # Extract from wrapped response
        assert len(data) == 3  # Only public lists

    def test_reading_lists_require_auth(self, client: TestClient):
        """Test that reading list endpoints require authentication"""
        # Test various endpoints without auth
        endpoints = [
            ("GET", "/api/v1/reading-lists/"),
            ("POST", "/api/v1/reading-lists/"),
            ("GET", "/api/v1/reading-lists/1"),
            ("PUT", "/api/v1/reading-lists/1"),
            ("DELETE", "/api/v1/reading-lists/1"),
        ]
        
        for method, endpoint in endpoints:
            response = client.request(method, endpoint)
            assert response.status_code in [401, 403]


class TestReadingListCRUD:
    """Test CRUD operations for reading lists"""

    def test_create_reading_list_crud(self, db_session: Session, test_user):
        """Test creating reading list via CRUD"""
        reading_list_data = ReadingListCreate(
            user_id=test_user.id,
            name="CRUD Test List",
            description="Created via CRUD",
            is_public=False,
            is_active=True
        )
        reading_list = crud_reading_list.create(db_session, obj_in=reading_list_data)
        
        assert reading_list.id is not None
        assert reading_list.name == "CRUD Test List"
        assert reading_list.user_id == test_user.id
        assert reading_list.is_active == True

    def test_get_by_user(self, db_session: Session, test_user):
        """Test getting reading lists by user"""
        # Create reading lists
        for i in range(3):
            reading_list_data = ReadingListCreate(
                user_id=test_user.id,
                name=f"User List {i}",
                description=f"Description {i}",
                is_public=i % 2 == 0,
                is_active=True
            )
            crud_reading_list.create(db_session, obj_in=reading_list_data)
        
        reading_lists = crud_reading_list.get_by_user(db_session, user_id=test_user.id)
        assert len(reading_lists) == 3

    def test_get_with_items(self, db_session: Session, test_user, test_book):
        """Test getting reading list with items"""
        # Create reading list
        reading_list_data = ReadingListCreate(
            user_id=test_user.id,
            name="List with Items",
            description="Description",
            is_public=False,
            is_active=True
        )
        reading_list = crud_reading_list.create(db_session, obj_in=reading_list_data)
        
        # Add book to list
        crud_reading_list_item.add_book_to_list(
            db_session, reading_list_id=reading_list.id, book_id=test_book.id
        )
        
        reading_list_with_items = crud_reading_list.get_with_items(
            db_session, id=reading_list.id  # Use 'id' parameter instead of 'reading_list_id'
        )
        assert reading_list_with_items is not None
        assert len(reading_list_with_items.items) == 1

    def test_add_book_to_list_crud(self, db_session: Session, test_user, test_book):
        """Test adding book to reading list via CRUD"""
        # Create reading list
        reading_list_data = ReadingListCreate(
            user_id=test_user.id,
            name="CRUD Book List",
            description="For CRUD testing",
            is_public=False,
            is_active=True
        )
        reading_list = crud_reading_list.create(db_session, obj_in=reading_list_data)
        
        # Add book
        item = crud_reading_list_item.add_book_to_list(
            db_session, reading_list_id=reading_list.id, book_id=test_book.id, notes="Test notes"
        )
        
        assert item.reading_list_id == reading_list.id
        assert item.book_id == test_book.id
        assert item.notes == "Test notes"
        assert item.order_index is not None

    def test_remove_book_from_list_crud(self, db_session: Session, test_user, test_book):
        """Test removing book from reading list via CRUD"""
        # Create reading list and add book
        reading_list_data = ReadingListCreate(
            user_id=test_user.id,
            name="CRUD Book List",
            description="For CRUD testing",
            is_public=False,
            is_active=True
        )
        reading_list = crud_reading_list.create(db_session, obj_in=reading_list_data)
        item = crud_reading_list_item.add_book_to_list(
            db_session, reading_list_id=reading_list.id, book_id=test_book.id
        )
        
        # Remove book
        removed_item = crud_reading_list_item.remove_book_from_list(
            db_session, reading_list_id=reading_list.id, book_id=test_book.id
        )
        
        assert removed_item.id == item.id
        
        # Verify it's removed
        remaining_items = crud_reading_list_item.get_by_reading_list(
            db_session, reading_list_id=reading_list.id
        )
        assert len(remaining_items) == 0

    def test_get_list_item_count(self, db_session: Session, test_user, test_book):
        """Test getting reading list item count"""
        # Create reading list
        reading_list_data = ReadingListCreate(
            user_id=test_user.id,
            name="Count Test List",
            description="For count testing",
            is_public=False,
            is_active=True
        )
        reading_list = crud_reading_list.create(db_session, obj_in=reading_list_data)
        
        # Initially should be 0
        count = crud_reading_list_item.get_list_item_count(db_session, reading_list_id=reading_list.id)
        assert count == 0
        
        # Add book
        crud_reading_list_item.add_book_to_list(
            db_session, reading_list_id=reading_list.id, book_id=test_book.id
        )
        
        # Count should be 1
        count = crud_reading_list_item.get_list_item_count(db_session, reading_list_id=reading_list.id)
        assert count == 1 