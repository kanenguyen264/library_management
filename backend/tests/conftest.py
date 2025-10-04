"""
Test configuration and fixtures for Book Reading API tests.
"""
import asyncio
import sqlite3
from typing import Any, Dict, Generator

import httpx
import pytest
import pytest_asyncio
from app.core.auth import create_access_token
from app.core.database import Base, get_db
from app.crud.author import crud_author
from app.crud.book import crud_book
from app.crud.category import crud_category
from app.crud.user import crud_user
from app.main import app
from app.models.author import Author
from app.models.book import Book
from app.models.category import Category
from app.models.user import User
from app.schemas.author import AuthorCreate
from app.schemas.book import BookCreate
from app.schemas.category import CategoryCreate
from app.schemas.user import UserCreate
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Use in-memory SQLite database for testing
TEST_DATABASE_URL = "sqlite:///:memory:"

# Create test engine with foreign key support enabled
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={
        "check_same_thread": False,
    },
    poolclass=StaticPool,
    echo=False,
)

# Add event listener to enable foreign keys for each connection
@event.listens_for(Engine, "connect")
def enable_sqlite_fks(dbapi_connection, connection_record):
    """Enable foreign key constraints in SQLite."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# Create test session
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test."""
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    # Create session
    session = TestingSessionLocal()
    
    try:
        yield session
    finally:
        session.close()
        # Drop tables after test
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session) -> Generator[TestClient, None, None]:
    """Create a test client with database session override."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def async_client(db_session) -> Generator[AsyncClient, None, None]:
    """Create an async test client."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest.fixture
def test_user_data() -> Dict[str, Any]:
    """Test user data."""
    return {
        "email": "test@example.com",
        "username": "testuser",
        "full_name": "Test User",
        "password": "testpassword123",
        "is_active": True,
        "is_admin": False,
    }


@pytest.fixture
def test_admin_data() -> Dict[str, Any]:
    """Test admin user data."""
    return {
        "email": "admin@example.com",
        "username": "adminuser",
        "full_name": "Admin User",
        "password": "adminpassword123",
        "is_active": True,
        "is_admin": True,
    }


@pytest.fixture
def test_user(db_session, test_user_data) -> User:
    """Create a test user."""
    user_in = UserCreate(**test_user_data)
    user = crud_user.create(db_session, obj_in=user_in)
    return user


@pytest.fixture
def test_user_2(db_session) -> User:
    """Create a second test user."""
    user_data = {
        "email": "user2@example.com",
        "username": "testuser2",
        "full_name": "Test User 2",
        "password": "testpass123",
        "is_active": True,
        "is_admin": False,
    }
    user_in = UserCreate(**user_data)
    user = crud_user.create(db_session, obj_in=user_in)
    return user


@pytest.fixture
def test_admin_user(db_session, test_admin_data) -> User:
    """Create a test admin user."""
    user_in = UserCreate(**test_admin_data)
    user = crud_user.create(db_session, obj_in=user_in)
    return user


@pytest.fixture
def user_token(test_user) -> str:
    """Generate JWT token for test user."""
    return create_access_token(test_user.id)


@pytest.fixture
def admin_token(test_admin_user) -> str:
    """Generate JWT token for test admin user."""
    return create_access_token(test_admin_user.id)


@pytest.fixture
def auth_headers(user_token) -> Dict[str, str]:
    """Authentication headers for regular user."""
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture
def admin_headers(admin_token) -> Dict[str, str]:
    """Authentication headers for admin user."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def test_author_data() -> Dict[str, Any]:
    """Test author data."""
    return {
        "name": "J.K. Rowling",
        "bio": "British author, best known for the Harry Potter series",
        "nationality": "British",
        "website": "https://www.jkrowling.com",
    }


@pytest.fixture
def test_author(db_session, test_author_data) -> Author:
    """Create a test author."""
    author_in = AuthorCreate(**test_author_data)
    author = crud_author.create(db_session, obj_in=author_in)
    return author


@pytest.fixture
def test_category_data() -> Dict[str, Any]:
    """Test category data."""
    return {
        "name": "Fantasy",
        "description": "Fantasy books and novels",
        "slug": "fantasy",
        "is_active": True,
    }


@pytest.fixture
def test_category(db_session, test_category_data) -> Category:
    """Create a test category."""
    category_in = CategoryCreate(**test_category_data)
    category = crud_category.create(db_session, obj_in=category_in)
    return category


@pytest.fixture
def test_book_data(test_author, test_category) -> Dict[str, Any]:
    """Test book data."""
    return {
        "title": "Harry Potter and the Philosopher's Stone",
        "isbn": "9780747532699",
        "description": "A young wizard's journey begins",
        "pages": 223,
        "language": "English",
        "is_free": True,
        "is_active": True,
        "author_id": test_author.id,
        "category_id": test_category.id,
    }


@pytest.fixture
def test_book(db_session, test_book_data) -> Book:
    """Create a test book."""
    book_in = BookCreate(**test_book_data)
    book = crud_book.create(db_session, obj_in=book_in)
    return book


@pytest.fixture  
def test_book_2(db_session, test_author, test_category) -> Book:
    """Create a second test book."""
    book_data = {
        "title": "The Chamber of Secrets",
        "isbn": "9780747538493",
        "description": "Harry's second year at Hogwarts",
        "pages": 251,
        "language": "English",
        "is_free": True,
        "is_active": True,
        "author_id": test_author.id,
        "category_id": test_category.id,
    }
    book_in = BookCreate(**book_data)
    book = crud_book.create(db_session, obj_in=book_in)
    return book


@pytest.fixture
def multiple_test_data(db_session):
    """Create multiple test entities for comprehensive testing."""
    # Create categories
    categories = []
    for i in range(3):
        category_data = {
            "name": f"Category {i+1}",
            "description": f"Description for category {i+1}",
            "slug": f"category-{i+1}",
            "is_active": True,
        }
        category = crud_category.create(db_session, obj_in=CategoryCreate(**category_data))
        categories.append(category)
    
    # Create authors
    authors = []
    for i in range(3):
        author_data = {
            "name": f"Author {i+1}",
            "bio": f"Biography for author {i+1}",
            "nationality": f"Country {i+1}",
        }
        author = crud_author.create(db_session, obj_in=AuthorCreate(**author_data))
        authors.append(author)
    
    # Create books
    books = []
    for i in range(5):
        book_data = {
            "title": f"Book {i+1}",
            "isbn": f"978074753269{i}",
            "description": f"Description for book {i+1}",
            "pages": 200 + i * 50,
            "language": "English",
            "is_free": i % 2 == 0,  # Every other book is free
            "is_active": True,
            "author_id": authors[i % len(authors)].id,
            "category_id": categories[i % len(categories)].id,
        }
        book = crud_book.create(db_session, obj_in=BookCreate(**book_data))
        books.append(book)
    
    return {
        "categories": categories,
        "authors": authors,
        "books": books,
    }


@pytest.fixture
def api_v1_prefix() -> str:
    """API v1 prefix."""
    return "/api/v1" 