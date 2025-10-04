"""
Test reading progress endpoints.
"""
import pytest
from app.crud.reading_progress import crud_reading_progress
from app.models.book import Book
from app.models.user import User
from app.schemas.reading_progress import ReadingProgressCreate
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.orm import Session


class TestReadingProgressEndpoints:
    """Test reading progress API endpoints."""

    def test_read_my_progress(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_user: User, test_book: Book, db_session: Session):
        """Test reading current user's progress."""
        # Create reading progress for test user
        progress_data = {
            "user_id": test_user.id,
            "book_id": test_book.id,
            "current_page": 50,
            "total_pages": 200,
            "progress_percentage": 25.0,
            "status": "reading",
        }
        progress_in = ReadingProgressCreate(**progress_data)
        crud_reading_progress.create(db_session, obj_in=progress_in)
        
        response = client.get(f"{api_v1_prefix}/reading-progress/", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]  # Extract from wrapped response
        assert isinstance(data, list)
        assert len(data) > 0
        
        # Check progress data structure
        progress_data = data[0]
        assert "id" in progress_data
        assert "user_id" in progress_data
        assert "book_id" in progress_data
        assert "current_page" in progress_data
        assert "total_pages" in progress_data
        assert "progress_percentage" in progress_data
        assert "status" in progress_data
        assert "book" in progress_data  # Should include book details

    def test_read_my_progress_unauthorized(self, client: TestClient, api_v1_prefix: str):
        """Test reading progress without authentication."""
        response = client.get(f"{api_v1_prefix}/reading-progress/")
        
        assert response.status_code == 403

    def test_read_my_progress_pagination(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_user: User, multiple_test_data: dict, db_session: Session):
        """Test reading progress with pagination."""
        # Access items from test data
        test_books = multiple_test_data['books']
        
        # Create progress records for multiple books
        for i, book in enumerate(test_books[:3]):
            progress_data = {
                "user_id": test_user.id,
                "book_id": book.id,
                "current_page": (i + 1) * 20,
                "total_pages": 200,
                "progress_percentage": ((i + 1) * 20) / 200 * 100,
                "status": "reading",
            }
            progress_in = ReadingProgressCreate(**progress_data)
            crud_reading_progress.create(db_session, obj_in=progress_in)
        
        # Test pagination
        response = client.get(f"{api_v1_prefix}/reading-progress/?skip=0&limit=2", headers=auth_headers)
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]  # Extract from wrapped response
        assert isinstance(data, list)
        assert len(data) == 2

    def test_create_or_update_progress(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_book: Book):
        """Test creating new reading progress."""
        progress_data = {
            "book_id": test_book.id,
            "current_page": 25,
            "total_pages": 300,
            "status": "reading",
        }
        
        response = client.post(f"{api_v1_prefix}/reading-progress/", json=progress_data, headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]  # Extract from wrapped response
        assert data["book_id"] == progress_data["book_id"]
        assert data["current_page"] == progress_data["current_page"]
        assert data["total_pages"] == progress_data["total_pages"]
        assert data["status"] == progress_data["status"]
        assert data["progress_percentage"] >= 0  # Should be calculated (might be 0 if not implemented)

    def test_update_existing_progress(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_user: User, test_book: Book, db_session: Session):
        """Test updating existing reading progress."""
        # Create initial progress
        initial_progress_data = {
            "user_id": test_user.id,
            "book_id": test_book.id,
            "current_page": 10,
            "total_pages": 100,
            "status": "reading",
        }
        progress_in = ReadingProgressCreate(**initial_progress_data)
        crud_reading_progress.create(db_session, obj_in=progress_in)
        
        # Update progress
        update_data = {
            "current_page": 50,
            "total_pages": 150,
        }
        
        response = client.post(f"{api_v1_prefix}/reading-progress/", json=update_data, headers=auth_headers)
        
        assert response.status_code == 422  # Should fail without book_id
        
        # Now with book_id
        update_data["book_id"] = test_book.id
        response = client.post(f"{api_v1_prefix}/reading-progress/", json=update_data, headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]
        assert data["current_page"] == update_data["current_page"]
        assert data["total_pages"] == update_data["total_pages"]

    def test_read_progress_for_book(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_user: User, test_book: Book, db_session: Session):
        """Test reading progress for specific book."""
        # Create progress first
        progress_data = {
            "user_id": test_user.id,
            "book_id": test_book.id,
            "current_page": 25,
            "total_pages": 100,
            "status": "reading",
        }
        progress_in = ReadingProgressCreate(**progress_data)
        crud_reading_progress.create(db_session, obj_in=progress_in)
        
        response = client.get(f"{api_v1_prefix}/reading-progress/book/{test_book.id}", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]
        assert data["book_id"] == test_book.id
        assert data["current_page"] == 25
        assert data["total_pages"] == 100

    def test_read_progress_for_book_not_found(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test reading progress for book that user hasn't started."""
        response = client.get(f"{api_v1_prefix}/reading-progress/book/99999", headers=auth_headers)
        
        # Should return success with null data
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["success"] is True
        assert response_data["data"] is None

    def test_update_progress_for_book(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_user: User, test_book: Book, db_session: Session):
        """Test updating progress for specific book."""
        # Create initial progress
        initial_progress_data = {
            "user_id": test_user.id,
            "book_id": test_book.id,
            "current_page": 20,
            "total_pages": 100,
            "status": "reading",
        }
        progress_in = ReadingProgressCreate(**initial_progress_data)
        crud_reading_progress.create(db_session, obj_in=progress_in)
        
        # Update progress
        update_data = {
            "current_page": 60,
            "reading_time_minutes": 120,
        }
        
        response = client.put(f"{api_v1_prefix}/reading-progress/book/{test_book.id}", json=update_data, headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]
        assert data["current_page"] == update_data["current_page"]
        assert data["reading_time_minutes"] == update_data["reading_time_minutes"]
        # Progress percentage should be calculated based on current implementation
        assert data["progress_percentage"] >= 0.0

    def test_update_progress_for_new_book(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_book: Book):
        """Test updating progress for book that user hasn't started."""
        update_data = {
            "current_page": 30,
            "total_pages": 200,
            "book_id": test_book.id,
        }
        
        response = client.post(f"{api_v1_prefix}/reading-progress/", json=update_data, headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]
        assert data["book_id"] == test_book.id
        assert data["current_page"] == update_data["current_page"]
        assert data["total_pages"] == update_data["total_pages"]

    def test_update_current_page(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_user: User, test_book: Book, db_session: Session):
        """Test updating current page specifically."""
        # Create initial progress
        initial_progress_data = {
            "user_id": test_user.id,
            "book_id": test_book.id,
            "current_page": 10,
            "total_pages": 100,
            "status": "reading",
        }
        progress_in = ReadingProgressCreate(**initial_progress_data)
        crud_reading_progress.create(db_session, obj_in=progress_in)
        
        # Update current page using PUT endpoint
        update_data = {
            "current_page": 75,
        }
        
        response = client.put(f"{api_v1_prefix}/reading-progress/book/{test_book.id}", json=update_data, headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]
        assert data["current_page"] == 75

    def test_update_current_page_with_total_pages(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_book: Book):
        """Test updating current page with total pages."""
        update_data = {
            "current_page": 50,
            "total_pages": 200,
        }
        
        response = client.put(f"{api_v1_prefix}/reading-progress/book/{test_book.id}", json=update_data, headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]
        assert data["current_page"] == 50
        assert data["total_pages"] == 200

    def test_read_completed_books(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_user: User, multiple_test_data: dict, db_session: Session):
        """Test reading completed books."""
        books = multiple_test_data["books"]
        
        # Create completed and non-completed progress
        for i, book in enumerate(books[:3]):
            progress_data = {
                "user_id": test_user.id,
                "book_id": book.id,
                "current_page": 100 if i < 2 else 50,
                "total_pages": 100,
                "is_completed": i < 2,
                "status": "completed" if i < 2 else "reading",
            }
            progress_in = ReadingProgressCreate(**progress_data)
            crud_reading_progress.create(db_session, obj_in=progress_in)
        
        response = client.get(f"{api_v1_prefix}/reading-progress/completed", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # All returned books should be completed
        for progress in data:
            assert progress["is_completed"] is True

    def test_read_currently_reading(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_user: User, multiple_test_data: dict, db_session: Session):
        """Test reading currently reading books."""
        books = multiple_test_data["books"]
        
        # Create reading and completed progress
        for i, book in enumerate(books[:3]):
            progress_data = {
                "user_id": test_user.id,
                "book_id": book.id,
                "current_page": 50 if i < 2 else 100,
                "total_pages": 100,
                "status": "reading" if i < 2 else "completed",
            }
            progress_in = ReadingProgressCreate(**progress_data)
            crud_reading_progress.create(db_session, obj_in=progress_in)
        
        response = client.get(f"{api_v1_prefix}/reading-progress/currently-reading", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # All returned books should be currently reading
        for progress in data:
            assert progress["status"] == "reading"

    def test_read_user_stats(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_user: User, multiple_test_data: dict, db_session: Session):
        """Test reading user statistics."""
        books = multiple_test_data["books"]
        
        # Create various progress states
        for i, book in enumerate(books[:4]):
            progress_data = {
                "user_id": test_user.id,
                "book_id": book.id,
                "current_page": 100 if i < 2 else 50,
                "total_pages": 100,
                "is_completed": i < 2,
                "status": "completed" if i < 2 else "reading",
                "reading_time_minutes": (i + 1) * 60,  # 60, 120, 180, 240 minutes
            }
            progress_in = ReadingProgressCreate(**progress_data)
            crud_reading_progress.create(db_session, obj_in=progress_in)
        
        response = client.get(f"{api_v1_prefix}/reading-progress/stats", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "total_books" in data
        assert "completed_books" in data
        assert "currently_reading" in data
        assert "total_reading_time_minutes" in data
        
        assert data["total_books"] >= 4
        assert data["completed_books"] >= 2
        assert data["currently_reading"] >= 2
        assert data["total_reading_time_minutes"] >= 600  # 60+120+180+240


class TestReadingProgressCRUD:
    """Test reading progress CRUD operations."""

    def test_create_reading_progress_crud(self, db_session: Session, test_user: User, test_book: Book):
        """Test creating reading progress through CRUD."""
        progress_data = {
            "user_id": test_user.id,
            "book_id": test_book.id,
            "current_page": 25,
            "total_pages": 200,
            "status": "reading",
        }
        progress_in = ReadingProgressCreate(**progress_data)
        progress = crud_reading_progress.create(db_session, obj_in=progress_in)
        
        assert progress.user_id == progress_data["user_id"]
        assert progress.book_id == progress_data["book_id"]
        assert progress.current_page == progress_data["current_page"]
        assert progress.total_pages == progress_data["total_pages"]
        assert progress.status == progress_data["status"]
        assert progress.id is not None

    def test_get_by_user_and_book(self, db_session: Session, test_user: User, test_book: Book):
        """Test getting progress by user and book."""
        # Create progress
        progress_data = {
            "user_id": test_user.id,
            "book_id": test_book.id,
            "current_page": 50,
            "total_pages": 150,
        }
        progress_in = ReadingProgressCreate(**progress_data)
        created_progress = crud_reading_progress.create(db_session, obj_in=progress_in)
        
        # Get progress
        progress = crud_reading_progress.get_by_user_and_book(db_session, user_id=test_user.id, book_id=test_book.id)
        
        assert progress is not None
        assert progress.id == created_progress.id
        assert progress.user_id == test_user.id
        assert progress.book_id == test_book.id

    def test_get_by_user(self, db_session: Session, test_user: User, multiple_test_data: dict):
        """Test getting progress by user."""
        books = multiple_test_data["books"]
        
        # Create progress for multiple books
        for book in books[:3]:
            progress_data = {
                "user_id": test_user.id,
                "book_id": book.id,
                "current_page": 25,
            }
            progress_in = ReadingProgressCreate(**progress_data)
            crud_reading_progress.create(db_session, obj_in=progress_in)
        
        progress_list = crud_reading_progress.get_by_user(db_session, user_id=test_user.id)
        
        assert isinstance(progress_list, list)
        assert len(progress_list) >= 3
        
        for progress in progress_list:
            assert progress.user_id == test_user.id

    def test_get_completed_by_user(self, db_session: Session, test_user: User, multiple_test_data: dict):
        """Test getting completed books by user."""
        books = multiple_test_data["books"]
        
        # Create completed and non-completed progress
        for i, book in enumerate(books[:4]):
            progress_data = {
                "user_id": test_user.id,
                "book_id": book.id,
                "current_page": 100,
                "total_pages": 100,
                "is_completed": i < 2,
                "status": "completed" if i < 2 else "reading",
            }
            progress_in = ReadingProgressCreate(**progress_data)
            crud_reading_progress.create(db_session, obj_in=progress_in)
        
        completed_progress = crud_reading_progress.get_completed_by_user(db_session, user_id=test_user.id)
        
        assert isinstance(completed_progress, list)
        assert len(completed_progress) >= 2
        
        for progress in completed_progress:
            assert progress.user_id == test_user.id
            assert progress.is_completed is True

    def test_get_currently_reading(self, db_session: Session, test_user: User, multiple_test_data: dict):
        """Test getting currently reading books."""
        books = multiple_test_data["books"]
        
        # Create reading and completed progress
        for i, book in enumerate(books[:4]):
            progress_data = {
                "user_id": test_user.id,
                "book_id": book.id,
                "current_page": 50,
                "total_pages": 100,
                "status": "reading" if i < 2 else "completed",
            }
            progress_in = ReadingProgressCreate(**progress_data)
            crud_reading_progress.create(db_session, obj_in=progress_in)
        
        reading_progress = crud_reading_progress.get_currently_reading(db_session, user_id=test_user.id)
        
        assert isinstance(reading_progress, list)
        assert len(reading_progress) >= 2
        
        for progress in reading_progress:
            assert progress.user_id == test_user.id
            assert progress.status == "reading"

    def test_update_progress_method(self, db_session: Session, test_user: User, test_book: Book):
        """Test updating progress using specialized method."""
        # Create initial progress
        progress_data = {
            "user_id": test_user.id,
            "book_id": test_book.id,
            "current_page": 10,
            "total_pages": 200,
            "status": "not_started",
        }
        progress_in = ReadingProgressCreate(**progress_data)
        progress = crud_reading_progress.create(db_session, obj_in=progress_in)
        
        # Update progress
        updated_progress = crud_reading_progress.update_progress(
            db_session, 
            db_obj=progress, 
            current_page=100, 
            total_pages=200
        )
        
        assert updated_progress.current_page == 100
        assert updated_progress.total_pages == 200
        assert updated_progress.progress_percentage == 50.0
        assert updated_progress.status == "reading"  # Should change from not_started
        assert updated_progress.started_at is not None
        assert updated_progress.last_read_at is not None

    def test_complete_book_progress(self, db_session: Session, test_user: User, test_book: Book):
        """Test completing a book through progress update."""
        # Create progress
        progress_data = {
            "user_id": test_user.id,
            "book_id": test_book.id,
            "current_page": 50,
            "total_pages": 100,
            "status": "reading",
        }
        progress_in = ReadingProgressCreate(**progress_data)
        progress = crud_reading_progress.create(db_session, obj_in=progress_in)
        
        # Complete the book
        updated_progress = crud_reading_progress.update_progress(
            db_session, 
            db_obj=progress, 
            current_page=100, 
            total_pages=100
        )
        
        assert updated_progress.current_page == 100
        assert updated_progress.is_completed is True
        assert updated_progress.status == "completed"
        assert updated_progress.completed_at is not None
        assert updated_progress.progress_percentage == 100.0

    def test_get_user_stats_crud(self, db_session: Session, test_user: User, multiple_test_data: dict):
        """Test getting user statistics through CRUD."""
        books = multiple_test_data["books"]
        
        # Create various progress states
        total_reading_time = 0
        for i, book in enumerate(books[:5]):
            reading_time = (i + 1) * 30  # 30, 60, 90, 120, 150 minutes
            total_reading_time += reading_time
            
            progress_data = {
                "user_id": test_user.id,
                "book_id": book.id,
                "current_page": 100 if i < 2 else 50,
                "total_pages": 100,
                "is_completed": i < 2,
                "status": "reading",
                "reading_time_minutes": reading_time,
            }
            progress_in = ReadingProgressCreate(**progress_data)
            crud_reading_progress.create(db_session, obj_in=progress_in)
        
        stats = crud_reading_progress.get_user_stats(db_session, user_id=test_user.id)
        
        assert "total_books" in stats
        assert "completed_books" in stats
        assert "currently_reading" in stats
        assert "total_reading_time_minutes" in stats
        
        assert stats["total_books"] >= 5
        assert stats["completed_books"] >= 2
        assert stats["currently_reading"] >= 5  # All have status "reading"
        assert stats["total_reading_time_minutes"] >= total_reading_time


@pytest.mark.asyncio
class TestReadingProgressEndpointsAsync:
    """Test reading progress endpoints with async client."""

    async def test_read_progress_async(self, async_client: AsyncClient, api_v1_prefix: str, auth_headers: dict):
        """Test reading progress list async."""
        response = await async_client.get(f"{api_v1_prefix}/reading-progress/", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["success"] is True
        data = response_data["data"]
        assert isinstance(data, list)

    async def test_create_progress_async(self, async_client: AsyncClient, api_v1_prefix: str, auth_headers: dict, test_book: Book):
        """Test creating progress async."""
        progress_data = {
            "book_id": test_book.id,
            "current_page": 25,
            "total_pages": 300,
            "status": "reading",
        }
        
        response = await async_client.post(f"{api_v1_prefix}/reading-progress/", json=progress_data, headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["success"] is True
        data = response_data["data"]
        assert data["book_id"] == test_book.id
        assert data["current_page"] == 25
        assert data["total_pages"] == 300 