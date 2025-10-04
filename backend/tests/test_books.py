"""
Test book management endpoints.
"""
import pytest
from app.crud.book import crud_book
from app.models.author import Author
from app.models.book import Book
from app.models.category import Category
from app.schemas.book import BookCreate
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.orm import Session


class TestBookEndpoints:
    """Test book management API endpoints."""

    def test_read_books_success(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_book: Book):
        """Test reading books list."""
        response = client.get(f"{api_v1_prefix}/books/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 0
        assert "meta" in data
        assert data["meta"]["total"] >= 0

    def test_read_books_unauthorized(self, client: TestClient, api_v1_prefix: str):
        """Test reading books without authentication."""
        response = client.get(f"{api_v1_prefix}/books/")
        
        assert response.status_code == 403

    def test_read_books_pagination(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, multiple_test_data: dict):
        """Test reading books with pagination."""
        response = client.get(f"{api_v1_prefix}/books/?skip=0&limit=3", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) <= 3
        assert data["meta"]["skip"] == 0
        assert data["meta"]["limit"] == 3

    def test_create_book_admin(self, client: TestClient, api_v1_prefix: str, admin_headers: dict, test_author: Author, test_category: Category):
        """Test creating book as admin."""
        book_data = {
            "title": "The Lord of the Rings",
            "isbn": "9780547928227",
            "description": "Epic fantasy novel",
            "pages": 1216,
            "language": "English",
            "is_free": False,
            "is_active": True,
            "author_id": test_author.id,
            "category_id": test_category.id,
        }

        response = client.post(f"{api_v1_prefix}/books/", json=book_data, headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["title"] == book_data["title"]
        assert data["data"]["isbn"] == book_data["isbn"]
        assert data["data"]["description"] == book_data["description"]
        assert data["data"]["author_id"] == book_data["author_id"]
        assert data["data"]["category_id"] == book_data["category_id"]

    def test_create_book_non_admin(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_author: Author, test_category: Category):
        """Test creating book as non-admin user."""
        book_data = {
            "title": "Unauthorized Book",
            "author_id": test_author.id,
            "category_id": test_category.id,
        }
        
        response = client.post(f"{api_v1_prefix}/books/", json=book_data, headers=auth_headers)
        
        assert response.status_code == 403

    def test_create_book_missing_required_fields(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test creating book without required fields."""
        book_data = {
            "description": "Book without title, author, or category",
        }
        
        response = client.post(f"{api_v1_prefix}/books/", json=book_data, headers=admin_headers)
        
        assert response.status_code == 422

    def test_create_book_invalid_author_id(self, client: TestClient, api_v1_prefix: str, admin_headers: dict, test_category: Category):
        """Test creating book with invalid author ID."""
        book_data = {
            "title": "Book with Invalid Author",
            "author_id": 99999,
            "category_id": test_category.id,
        }
        
        response = client.post(f"{api_v1_prefix}/books/", json=book_data, headers=admin_headers)
        
        # Should return 400 or 422 due to foreign key constraint
        assert response.status_code in [400, 422]

    def test_create_book_invalid_category_id(self, client: TestClient, api_v1_prefix: str, admin_headers: dict, test_author: Author):
        """Test creating book with invalid category ID."""
        book_data = {
            "title": "Book with Invalid Category",
            "author_id": test_author.id,
            "category_id": 99999,
        }
        
        response = client.post(f"{api_v1_prefix}/books/", json=book_data, headers=admin_headers)
        
        # Should return 400 or 422 due to foreign key constraint
        assert response.status_code in [400, 422]

    def test_read_book_by_id_success(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_book: Book):
        """Test reading book by ID with details."""
        response = client.get(f"{api_v1_prefix}/books/{test_book.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["id"] == test_book.id
        assert data["data"]["title"] == test_book.title
        assert data["data"]["author_id"] == test_book.author_id
        assert data["data"]["category_id"] == test_book.category_id
        # Should include author and category details
        assert "author" in data["data"]
        assert "category" in data["data"]

    def test_read_book_by_id_not_found(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test reading non-existent book by ID."""
        response = client.get(f"{api_v1_prefix}/books/99999", headers=auth_headers)
        
        assert response.status_code == 404

    def test_read_book_by_id_unauthorized(self, client: TestClient, api_v1_prefix: str, test_book: Book):
        """Test reading book by ID without authentication."""
        response = client.get(f"{api_v1_prefix}/books/{test_book.id}")
        
        assert response.status_code == 403

    def test_update_book_admin(self, client: TestClient, api_v1_prefix: str, admin_headers: dict, test_book: Book):
        """Test updating book as admin."""
        update_data = {
            "title": "Updated Book Title",
            "description": "Updated description",
            "pages": 500,
            "is_free": True,
        }

        response = client.put(f"{api_v1_prefix}/books/{test_book.id}", json=update_data, headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["title"] == update_data["title"]
        assert data["data"]["description"] == update_data["description"]
        assert data["data"]["pages"] == update_data["pages"]
        assert data["data"]["is_free"] == update_data["is_free"]

    def test_update_book_non_admin(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_book: Book):
        """Test updating book as non-admin user."""
        update_data = {
            "title": "Unauthorized Update",
        }
        
        response = client.put(f"{api_v1_prefix}/books/{test_book.id}", json=update_data, headers=auth_headers)
        
        assert response.status_code == 403

    def test_update_book_not_found(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test updating non-existent book."""
        update_data = {
            "title": "Updated Title",
        }
        
        response = client.put(f"{api_v1_prefix}/books/99999", json=update_data, headers=admin_headers)
        
        assert response.status_code == 404

    def test_delete_book_admin(self, client: TestClient, api_v1_prefix: str, admin_headers: dict, db_session: Session, test_author: Author, test_category: Category):
        """Test deleting book as admin."""
        # Create book to delete
        book_data = {
            "title": "Book to Delete",
            "description": "This book will be deleted",
            "author_id": test_author.id,
            "category_id": test_category.id,
        }
        book_in = BookCreate(**book_data)
        book = crud_book.create(db_session, obj_in=book_in)

        response = client.delete(f"{api_v1_prefix}/books/{book.id}", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data

    def test_delete_book_non_admin(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_book: Book):
        """Test deleting book as non-admin user."""
        response = client.delete(f"{api_v1_prefix}/books/{test_book.id}", headers=auth_headers)
        
        assert response.status_code == 403

    def test_delete_book_not_found(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test deleting non-existent book."""
        response = client.delete(f"{api_v1_prefix}/books/99999", headers=admin_headers)
        
        assert response.status_code == 404

    def test_read_books_by_author(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_author: Author):
        """Test reading books by author."""
        response = client.get(f"{api_v1_prefix}/books/author/{test_author.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert data["meta"]["total"] >= 0

    def test_read_books_by_author_pagination(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_author: Author):
        """Test reading books by author with pagination."""
        response = client.get(f"{api_v1_prefix}/books/author/{test_author.id}?skip=0&limit=3", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert data["meta"]["total"] >= 0
        assert data["meta"]["skip"] == 0
        assert data["meta"]["limit"] == 3

    def test_read_books_by_category(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_category: Category):
        """Test reading books by category."""
        response = client.get(f"{api_v1_prefix}/books/category/{test_category.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert data["meta"]["total"] >= 0

    def test_read_books_by_category_pagination(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_category: Category):
        """Test reading books by category with pagination."""
        response = client.get(f"{api_v1_prefix}/books/category/{test_category.id}?skip=0&limit=3", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert data["meta"]["total"] >= 0
        assert data["meta"]["skip"] == 0
        assert data["meta"]["limit"] == 3

    def test_read_free_books(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, multiple_test_data: dict):
        """Test reading free books."""
        response = client.get(f"{api_v1_prefix}/books/free", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert data["meta"]["total"] >= 0

    def test_read_free_books_pagination(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test reading free books with pagination."""
        response = client.get(f"{api_v1_prefix}/books/free?skip=0&limit=3", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert data["meta"]["total"] >= 0
        assert data["meta"]["skip"] == 0
        assert data["meta"]["limit"] == 3

    def test_read_books_by_nonexistent_author(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test reading books by non-existent author."""
        response = client.get(f"{api_v1_prefix}/books/author/99999", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 0  # Should be empty for non-existent author
        assert data["meta"]["total"] == 0

    def test_read_books_by_nonexistent_category(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test reading books by non-existent category."""
        response = client.get(f"{api_v1_prefix}/books/category/99999", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 0  # Should be empty for non-existent category
        assert data["meta"]["total"] == 0


class TestBookCRUD:
    """Test book CRUD operations."""

    def test_create_book_crud(self, db_session: Session, test_author: Author, test_category: Category):
        """Test creating book through CRUD."""
        book_data = {
            "title": "CRUD Book",
            "isbn": "9781234567890",
            "description": "Book created through CRUD",
            "pages": 300,
            "language": "English",
            "is_free": True,
            "is_active": True,
            "author_id": test_author.id,
            "category_id": test_category.id,
        }
        book_in = BookCreate(**book_data)
        book = crud_book.create(db_session, obj_in=book_in)
        
        assert book.title == book_data["title"]
        assert book.isbn == book_data["isbn"]
        assert book.description == book_data["description"]
        assert book.pages == book_data["pages"]
        assert book.language == book_data["language"]
        assert book.is_free == book_data["is_free"]
        assert book.is_active == book_data["is_active"]
        assert book.author_id == book_data["author_id"]
        assert book.category_id == book_data["category_id"]
        assert book.id is not None

    def test_get_book_with_details(self, db_session: Session, test_book: Book):
        """Test getting book with author and category details."""
        book = crud_book.get_with_details(db_session, id=test_book.id)
        
        assert book is not None
        assert book.id == test_book.id
        assert book.title == test_book.title
        # Should have author and category loaded
        assert book.author is not None
        assert book.category is not None

    def test_get_multi_books_with_details(self, db_session: Session, multiple_test_data: dict):
        """Test getting multiple books with details."""
        books = crud_book.get_multi_with_details(db_session, skip=0, limit=3)
        
        assert isinstance(books, list)
        assert len(books) <= 3
        
        for book in books:
            assert book.author is not None
            assert book.category is not None

    def test_get_book_by_title(self, db_session: Session, test_book: Book):
        """Test getting book by title."""
        book = crud_book.get_by_title(db_session, title=test_book.title)
        
        assert book is not None
        assert book.title == test_book.title
        assert book.id == test_book.id

    def test_get_book_by_title_not_found(self, db_session: Session):
        """Test getting book by non-existent title."""
        book = crud_book.get_by_title(db_session, title="Nonexistent Book")
        
        assert book is None

    def test_get_book_by_isbn(self, db_session: Session, test_book: Book):
        """Test getting book by ISBN."""
        book = crud_book.get_by_isbn(db_session, isbn=test_book.isbn)
        
        assert book is not None
        assert book.isbn == test_book.isbn
        assert book.id == test_book.id

    def test_get_book_by_isbn_not_found(self, db_session: Session):
        """Test getting book by non-existent ISBN."""
        book = crud_book.get_by_isbn(db_session, isbn="9999999999999")
        
        assert book is None

    def test_get_books_by_author(self, db_session: Session, test_author: Author, test_category: Category):
        """Test getting books by author."""
        # Create additional books for the same author
        for i in range(3):
            book_data = {
                "title": f"Author Book {i}",
                "isbn": f"978123456789{i}",
                "author_id": test_author.id,
                "category_id": test_category.id,
            }
            book_in = BookCreate(**book_data)
            crud_book.create(db_session, obj_in=book_in)
        
        books = crud_book.get_by_author(db_session, author_id=test_author.id)
        
        assert isinstance(books, list)
        assert len(books) >= 3
        
        for book in books:
            assert book.author_id == test_author.id

    def test_get_books_by_category(self, db_session: Session, test_author: Author, test_category: Category):
        """Test getting books by category."""
        # Create additional books for the same category
        for i in range(3):
            book_data = {
                "title": f"Category Book {i}",
                "isbn": f"978987654321{i}",
                "author_id": test_author.id,
                "category_id": test_category.id,
            }
            book_in = BookCreate(**book_data)
            crud_book.create(db_session, obj_in=book_in)
        
        books = crud_book.get_by_category(db_session, category_id=test_category.id)
        
        assert isinstance(books, list)
        assert len(books) >= 3
        
        for book in books:
            assert book.category_id == test_category.id

    def test_get_free_books(self, db_session: Session, test_author: Author, test_category: Category):
        """Test getting free books."""
        # Create free and paid books
        for i in range(2):
            book_data = {
                "title": f"Free Book {i}",
                "isbn": f"978111111111{i}",
                "is_free": True,
                "is_active": True,
                "author_id": test_author.id,
                "category_id": test_category.id,
            }
            book_in = BookCreate(**book_data)
            crud_book.create(db_session, obj_in=book_in)
        
        for i in range(2):
            book_data = {
                "title": f"Paid Book {i}",
                "isbn": f"978222222222{i}",
                "is_free": False,
                "is_active": True,
                "author_id": test_author.id,
                "category_id": test_category.id,
            }
            book_in = BookCreate(**book_data)
            crud_book.create(db_session, obj_in=book_in)
        
        free_books = crud_book.get_free_books(db_session)
        
        assert isinstance(free_books, list)
        assert len(free_books) >= 2
        
        for book in free_books:
            assert book.is_free is True
            assert book.is_active is True

    def test_search_books(self, db_session: Session, test_book: Book):
        """Test searching books by title or description."""
        search_term = test_book.title.split()[0]
        books = crud_book.search_books(db_session, query=search_term)
        
        assert isinstance(books, list)
        assert len(books) > 0
        found_book = any(book.id == test_book.id for book in books)
        assert found_book

    def test_search_books_no_results(self, db_session: Session):
        """Test searching books with no results."""
        books = crud_book.search_books(db_session, query="NonexistentBookTitle")
        
        assert isinstance(books, list)
        assert len(books) == 0

    def test_get_active_books(self, db_session: Session, test_author: Author, test_category: Category):
        """Test getting active books."""
        # Create active and inactive books
        for i in range(2):
            book_data = {
                "title": f"Active Book {i}",
                "isbn": f"978333333333{i}",
                "is_active": True,
                "author_id": test_author.id,
                "category_id": test_category.id,
            }
            book_in = BookCreate(**book_data)
            crud_book.create(db_session, obj_in=book_in)
        
        for i in range(2):
            book_data = {
                "title": f"Inactive Book {i}",
                "isbn": f"978444444444{i}",
                "is_active": False,
                "author_id": test_author.id,
                "category_id": test_category.id,
            }
            book_in = BookCreate(**book_data)
            crud_book.create(db_session, obj_in=book_in)
        
        active_books = crud_book.get_active_books(db_session)
        
        assert isinstance(active_books, list)
        assert len(active_books) >= 2
        
        for book in active_books:
            assert book.is_active is True


@pytest.mark.asyncio
class TestBookEndpointsAsync:
    """Test book endpoints with async client."""

    async def test_read_books_async(self, async_client: AsyncClient, api_v1_prefix: str, auth_headers: dict):
        """Test reading books list async."""
        response = await async_client.get(f"{api_v1_prefix}/books/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert "meta" in data
        assert data["meta"]["total"] >= 0

    async def test_create_book_async(self, async_client: AsyncClient, api_v1_prefix: str, admin_headers: dict, test_author: Author, test_category: Category):
        """Test creating book async."""
        book_data = {
            "title": "Async Book",
            "description": "Book created asynchronously",
            "author_id": test_author.id,
            "category_id": test_category.id,
        }

        response = await async_client.post(f"{api_v1_prefix}/books/", json=book_data, headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["title"] == book_data["title"]
        assert data["data"]["description"] == book_data["description"]
        assert data["data"]["author_id"] == book_data["author_id"]
        assert data["data"]["category_id"] == book_data["category_id"] 