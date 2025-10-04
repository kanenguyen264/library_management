"""
Test chapter management endpoints.
"""
import pytest
from app.crud.chapter import crud_chapter
from app.models.book import Book
from app.models.chapter import Chapter
from app.schemas.chapter import ChapterCreate
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.orm import Session


@pytest.fixture
def test_chapter_data(test_book: Book) -> dict:
    """Test chapter data."""
    return {
        "title": "Chapter 1: The Beginning",
        "content": "This is the opening chapter with compelling content...",
        "chapter_number": 1,
        "book_id": test_book.id,
        "is_published": True,
        "is_active": True,
    }


@pytest.fixture
def test_chapter(db_session: Session, test_chapter_data: dict) -> Chapter:
    """Create a test chapter."""
    chapter_in = ChapterCreate(**test_chapter_data)
    return crud_chapter.create(db_session, obj_in=chapter_in)


@pytest.fixture
def multiple_chapters(db_session: Session, test_book: Book) -> list[Chapter]:
    """Create multiple test chapters."""
    chapters = []
    for i in range(1, 6):
        chapter_data = {
            "title": f"Chapter {i}: Part {i}",
            "content": f"Content for chapter {i}...",
            "chapter_number": i,
            "book_id": test_book.id,
            "is_published": i <= 3,  # First 3 are published
            "is_active": True,
        }
        chapter_in = ChapterCreate(**chapter_data)
        chapter = crud_chapter.create(db_session, obj_in=chapter_in)
        chapters.append(chapter)
    return chapters


class TestChapterEndpoints:
    """Test chapter management API endpoints."""

    def test_read_chapters_success(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_chapter: Chapter):
        """Test reading chapters list with details."""
        response = client.get(f"{api_v1_prefix}/chapters/", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) > 0
        
        # Check chapter data structure
        chapter_data = data["data"][0]
        assert "id" in chapter_data
        assert "title" in chapter_data
        assert "content" in chapter_data
        assert "chapter_number" in chapter_data
        assert "is_published" in chapter_data
        assert "is_active" in chapter_data
        assert "book_id" in chapter_data
        assert "created_at" in chapter_data

    def test_read_chapters_unauthorized(self, client: TestClient, api_v1_prefix: str):
        """Test reading chapters without authentication."""
        response = client.get(f"{api_v1_prefix}/chapters/")
        
        assert response.status_code == 403

    def test_read_chapters_pagination(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, multiple_chapters: list):
        """Test reading chapters with pagination."""
        response = client.get(f"{api_v1_prefix}/chapters/?skip=0&limit=3", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) <= 3

    def test_create_chapter_admin(self, client: TestClient, api_v1_prefix: str, admin_headers: dict, test_book):
        """Test creating chapter as admin."""
        chapter_data = {
            "title": "New Chapter Title",
            "content": "Chapter content here",
            "chapter_number": 2,
            "image_url": "https://example.com/chapter.jpg",
            "is_published": True,
            "is_active": True,
            "book_id": test_book.id,
        }
        
        response = client.post(f"{api_v1_prefix}/chapters/", json=chapter_data, headers=admin_headers)
        
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["title"] == chapter_data["title"]
        assert data["data"]["content"] == chapter_data["content"]
        assert data["data"]["chapter_number"] == chapter_data["chapter_number"]
        assert data["data"]["book_id"] == chapter_data["book_id"]
        assert "id" in data["data"]
        assert "created_at" in data["data"]

    def test_create_chapter_non_admin(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_book):
        """Test creating chapter as non-admin user."""
        chapter_data = {
            "title": "Unauthorized Chapter",
            "content": "Should not be created",
            "chapter_number": 99,
            "book_id": test_book.id,
        }
        
        response = client.post(f"{api_v1_prefix}/chapters/", json=chapter_data, headers=auth_headers)
        
        assert response.status_code == 403

    def test_create_chapter_missing_book(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test creating chapter without book ID."""
        chapter_data = {
            "title": "Chapter Without Book",
            "content": "Content",
            "chapter_number": 1,
        }
        
        response = client.post(f"{api_v1_prefix}/chapters/", json=chapter_data, headers=admin_headers)
        
        assert response.status_code == 422

    def test_create_chapter_duplicate_number(self, client: TestClient, api_v1_prefix: str, admin_headers: dict, test_chapter: Chapter):
        """Test creating chapter with duplicate chapter number for same book."""
        chapter_data = {
            "title": "Duplicate Chapter",
            "content": "Duplicate content",
            "chapter_number": test_chapter.chapter_number,
            "book_id": test_chapter.book_id,
        }
        
        response = client.post(f"{api_v1_prefix}/chapters/", json=chapter_data, headers=admin_headers)
        
        assert response.status_code == 400

    def test_read_chapter_by_id_success(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_chapter: Chapter):
        """Test reading chapter by ID."""
        response = client.get(f"{api_v1_prefix}/chapters/{test_chapter.id}", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["id"] == test_chapter.id
        assert data["data"]["title"] == test_chapter.title
        assert data["data"]["chapter_number"] == test_chapter.chapter_number
        assert data["data"]["book_id"] == test_chapter.book_id

    def test_read_chapter_by_id_not_found(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test reading non-existent chapter by ID."""
        response = client.get(f"{api_v1_prefix}/chapters/99999", headers=auth_headers)
        
        assert response.status_code == 404

    def test_read_chapter_by_id_unauthorized(self, client: TestClient, api_v1_prefix: str, test_chapter: Chapter):
        """Test reading chapter by ID without authentication."""
        response = client.get(f"{api_v1_prefix}/chapters/{test_chapter.id}")
        
        assert response.status_code == 403

    def test_update_chapter_admin(self, client: TestClient, api_v1_prefix: str, admin_headers: dict, test_chapter: Chapter):
        """Test updating chapter as admin."""
        update_data = {
            "title": "Updated Chapter Title",
            "content": "Updated content",
            "is_published": True,
        }
        
        response = client.put(f"{api_v1_prefix}/chapters/{test_chapter.id}", json=update_data, headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["title"] == update_data["title"]
        assert data["data"]["content"] == update_data["content"]
        assert data["data"]["is_published"] == update_data["is_published"]

    def test_update_chapter_non_admin(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_chapter: Chapter):
        """Test updating chapter as non-admin user."""
        update_data = {
            "title": "Unauthorized Update",
        }
        
        response = client.put(f"{api_v1_prefix}/chapters/{test_chapter.id}", json=update_data, headers=auth_headers)
        
        assert response.status_code == 403

    def test_update_chapter_not_found(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test updating non-existent chapter."""
        update_data = {
            "title": "Updated Title",
        }
        
        response = client.put(f"{api_v1_prefix}/chapters/99999", json=update_data, headers=admin_headers)
        
        assert response.status_code == 404

    def test_delete_chapter_admin(self, client: TestClient, api_v1_prefix: str, admin_headers: dict, db_session: Session, test_book):
        """Test deleting chapter as admin."""
        # Create chapter to delete
        chapter_data = {
            "title": "Chapter to Delete",
            "content": "Content to be deleted",
            "chapter_number": 99,
            "book_id": test_book.id,
        }
        chapter_in = ChapterCreate(**chapter_data)
        chapter = crud_chapter.create(db_session, obj_in=chapter_in)
        
        response = client.delete(f"{api_v1_prefix}/chapters/{chapter.id}", headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data

    def test_delete_chapter_non_admin(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_chapter: Chapter):
        """Test deleting chapter as non-admin user."""
        response = client.delete(f"{api_v1_prefix}/chapters/{test_chapter.id}", headers=auth_headers)
        
        assert response.status_code == 403

    def test_delete_chapter_not_found(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test deleting non-existent chapter."""
        response = client.delete(f"{api_v1_prefix}/chapters/99999", headers=admin_headers)
        
        assert response.status_code == 404

    def test_read_chapters_by_book_success(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_chapter: Chapter):
        """Test reading chapters by book ID."""
        response = client.get(f"{api_v1_prefix}/chapters/book/{test_chapter.book_id}", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) > 0
        
        # All chapters should belong to the same book
        for chapter in data["data"]:
            assert chapter["book_id"] == test_chapter.book_id

    def test_read_chapters_by_book_pagination(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_book: Book, multiple_chapters: list):
        """Test reading chapters by book with pagination."""
        response = client.get(f"{api_v1_prefix}/chapters/book/{test_book.id}?skip=0&limit=3", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 3

    def test_read_published_chapters_by_book_success(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_chapter: Chapter):
        """Test reading published chapters by book ID."""
        response = client.get(f"{api_v1_prefix}/chapters/published/book/{test_chapter.book_id}", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        
        # Verify all returned chapters are published
        for chapter in data["data"]:
            assert chapter["is_published"] is True
            assert chapter["book_id"] == test_chapter.book_id

    def test_read_chapters_by_book_not_found(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test reading chapters for non-existent book."""
        response = client.get(f"{api_v1_prefix}/chapters/book/99999", headers=auth_headers)
        
        assert response.status_code == 404


class TestChapterCRUD:
    """Test chapter CRUD operations."""

    def test_create_chapter_crud(self, db_session: Session, test_book: Book):
        """Test creating chapter via CRUD."""
        chapter_data = {
            "title": "CRUD Test Chapter",
            "content": "Content for CRUD testing",
            "chapter_number": 99,
            "book_id": test_book.id,
            "is_published": True,
            "is_active": True,
        }
        
        chapter_in = ChapterCreate(**chapter_data)
        chapter = crud_chapter.create(db_session, obj_in=chapter_in)
        
        assert chapter.title == chapter_data["title"]
        assert chapter.content == chapter_data["content"]
        assert chapter.chapter_number == chapter_data["chapter_number"]
        assert chapter.book_id == chapter_data["book_id"]
        assert chapter.is_published == chapter_data["is_published"]
        assert chapter.is_active == chapter_data["is_active"]
        assert chapter.id is not None

    def test_get_chapter_with_details(self, db_session: Session, test_chapter: Chapter):
        """Test getting chapter with book details."""
        chapter = crud_chapter.get_with_details(db_session, id=test_chapter.id)
        
        assert chapter is not None
        assert chapter.id == test_chapter.id
        assert hasattr(chapter, 'book')
        assert chapter.book is not None

    def test_get_multi_chapters_with_details(self, db_session: Session, multiple_chapters: list):
        """Test getting multiple chapters with details."""
        chapters = crud_chapter.get_multi_with_details(db_session, skip=0, limit=10)
        
        assert len(chapters) > 0
        for chapter in chapters:
            assert hasattr(chapter, 'book')

    def test_get_chapters_by_book(self, db_session: Session, test_book: Book, multiple_chapters: list):
        """Test getting chapters by book ID."""
        chapters = crud_chapter.get_by_book(db_session, book_id=test_book.id)
        
        assert len(chapters) == 5
        for chapter in chapters:
            assert chapter.book_id == test_book.id
        
        # Check ordering by chapter_number
        for i in range(1, len(chapters)):
            assert chapters[i-1].chapter_number <= chapters[i].chapter_number

    def test_get_chapter_by_book_and_number(self, db_session: Session, test_chapter: Chapter):
        """Test getting chapter by book ID and chapter number."""
        chapter = crud_chapter.get_by_book_and_chapter_number(
            db_session, book_id=test_chapter.book_id, chapter_number=test_chapter.chapter_number
        )
        
        assert chapter is not None
        assert chapter.id == test_chapter.id

    def test_get_chapter_by_book_and_number_not_found(self, db_session: Session, test_book: Book):
        """Test getting non-existent chapter by book and number."""
        chapter = crud_chapter.get_by_book_and_chapter_number(
            db_session, book_id=test_book.id, chapter_number=999
        )
        
        assert chapter is None

    def test_get_published_chapters(self, db_session: Session, test_book: Book, multiple_chapters: list):
        """Test getting only published chapters."""
        chapters = crud_chapter.get_published_chapters(db_session, book_id=test_book.id)
        
        assert len(chapters) == 3  # Only first 3 are published
        for chapter in chapters:
            assert chapter.is_published is True
            assert chapter.is_active is True

    def test_get_active_chapters(self, db_session: Session, multiple_chapters: list):
        """Test getting only active chapters."""
        chapters = crud_chapter.get_active_chapters(db_session)
        
        assert len(chapters) > 0
        for chapter in chapters:
            assert chapter.is_active is True

    def test_search_chapters(self, db_session: Session, test_chapter: Chapter):
        """Test searching chapters by content."""
        chapters = crud_chapter.search_chapters(db_session, query="Beginning")
        
        assert len(chapters) > 0
        # At least one chapter should contain "Beginning"
        found = False
        for chapter in chapters:
            if "Beginning" in chapter.title or "Beginning" in (chapter.content or ""):
                found = True
                break
        assert found

    def test_search_chapters_no_results(self, db_session: Session):
        """Test searching chapters with no results."""
        chapters = crud_chapter.search_chapters(db_session, query="nonexistentkeyword")
        
        assert len(chapters) == 0


@pytest.mark.asyncio
class TestChapterEndpointsAsync:
    """Test chapter endpoints with async client."""

    async def test_read_chapters_async(self, async_client: AsyncClient, api_v1_prefix: str, auth_headers: dict):
        """Test reading chapters asynchronously."""
        response = await async_client.get(f"{api_v1_prefix}/chapters/", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)

    async def test_create_chapter_async(self, async_client: AsyncClient, api_v1_prefix: str, admin_headers: dict, test_book: Book):
        """Test creating chapter asynchronously."""
        chapter_data = {
            "title": "Async Test Chapter",
            "content": "Content for async testing",
            "chapter_number": 88,
            "book_id": test_book.id,
            "is_published": True,
            "is_active": True,
        }
        
        response = await async_client.post(f"{api_v1_prefix}/chapters/", json=chapter_data, headers=admin_headers)
        
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["title"] == chapter_data["title"]
        assert data["data"]["chapter_number"] == chapter_data["chapter_number"] 