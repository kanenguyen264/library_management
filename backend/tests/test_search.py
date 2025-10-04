"""
Test search endpoints.
"""
import pytest
from app.models.author import Author
from app.models.book import Book
from app.models.category import Category
from fastapi.testclient import TestClient
from httpx import AsyncClient


class TestSearchEndpoints:
    """Test search API endpoints."""

    def test_search_books_success(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_book: Book):
        """Test searching books by title or description."""
        search_term = test_book.title.split()[0]  # First word of title
        
        response = client.get(f"{api_v1_prefix}/search/books?q={search_term}", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["success"] is True
        assert "message" in response_data
        data = response_data["data"]
        assert isinstance(data, list)
        assert len(data) > 0
        
        # Check if search result contains the book
        found_book = any(book["id"] == test_book.id for book in data)
        assert found_book
        
        # Check book data structure with details
        book_data = data[0]
        assert "id" in book_data
        assert "title" in book_data
        assert "author" in book_data
        assert "category" in book_data

    def test_search_books_by_description(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_book: Book):
        """Test searching books by description."""
        if test_book.description:
            search_term = test_book.description.split()[0]  # First word of description
            
            response = client.get(f"{api_v1_prefix}/search/books?q={search_term}", headers=auth_headers)
            
            assert response.status_code == 200
            response_data = response.json()
            data = response_data["data"]
            assert isinstance(data, list)

    def test_search_books_no_results(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test searching books with no results."""
        response = client.get(f"{api_v1_prefix}/search/books?q=nonexistentbooktitle", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]
        assert isinstance(data, list)
        assert len(data) == 0

    def test_search_books_empty_query(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test searching books with empty query."""
        response = client.get(f"{api_v1_prefix}/search/books?q=", headers=auth_headers)
        
        assert response.status_code == 422

    def test_search_books_pagination(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, multiple_test_data: dict):
        """Test searching books with pagination."""
        # Use a common word that might appear in multiple books
        search_term = "Book"  # This should match multiple books from test data
        
        response = client.get(f"{api_v1_prefix}/search/books?q={search_term}&skip=0&limit=3", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]
        assert isinstance(data, list)
        assert len(data) <= 3

    def test_search_books_unauthorized(self, client: TestClient, api_v1_prefix: str):
        """Test searching books without authentication."""
        response = client.get(f"{api_v1_prefix}/search/books?q=test")
        
        assert response.status_code == 403

    def test_search_authors_success(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_author: Author):
        """Test searching authors by name."""
        search_term = test_author.name.split()[0]  # First word of name
        
        response = client.get(f"{api_v1_prefix}/search/authors?q={search_term}", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["success"] is True
        assert "message" in response_data
        data = response_data["data"]
        assert isinstance(data, list)
        assert len(data) > 0
        
        # Check if search result contains the author
        found_author = any(author["id"] == test_author.id for author in data)
        assert found_author
        
        # Check author data structure
        author_data = data[0]
        assert "id" in author_data
        assert "name" in author_data
        assert "bio" in author_data
        assert "nationality" in author_data

    def test_search_authors_no_results(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test searching authors with no results."""
        response = client.get(f"{api_v1_prefix}/search/authors?q=nonexistentauthor", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]
        assert isinstance(data, list)
        assert len(data) == 0

    def test_search_authors_empty_query(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test searching authors with empty query."""
        response = client.get(f"{api_v1_prefix}/search/authors?q=", headers=auth_headers)
        
        assert response.status_code == 422

    def test_search_authors_pagination(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, multiple_test_data: dict):
        """Test searching authors with pagination."""
        # Use a common word that might appear in multiple authors
        search_term = "Author"  # This should match multiple authors from test data
        
        response = client.get(f"{api_v1_prefix}/search/authors?q={search_term}&skip=0&limit=2", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]
        assert isinstance(data, list)
        assert len(data) <= 2

    def test_search_authors_unauthorized(self, client: TestClient, api_v1_prefix: str):
        """Test searching authors without authentication."""
        response = client.get(f"{api_v1_prefix}/search/authors?q=test")
        
        assert response.status_code == 403

    def test_search_categories_success(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_category: Category):
        """Test searching categories by name."""
        search_term = test_category.name.split()[0]  # First word of name
        
        response = client.get(f"{api_v1_prefix}/search/categories?q={search_term}", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["success"] is True
        assert "message" in response_data
        data = response_data["data"]
        assert isinstance(data, list)
        assert len(data) > 0
        
        # Check if search result contains the category
        found_category = any(category["id"] == test_category.id for category in data)
        assert found_category
        
        # Check category data structure
        category_data = data[0]
        assert "id" in category_data
        assert "name" in category_data
        assert "description" in category_data
        assert "slug" in category_data
        assert "is_active" in category_data

    def test_search_categories_no_results(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test searching categories with no results."""
        response = client.get(f"{api_v1_prefix}/search/categories?q=nonexistentcategory", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]
        assert isinstance(data, list)
        assert len(data) == 0

    def test_search_categories_empty_query(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test searching categories with empty query."""
        response = client.get(f"{api_v1_prefix}/search/categories?q=", headers=auth_headers)
        
        assert response.status_code == 422

    def test_search_categories_pagination(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, multiple_test_data: dict):
        """Test searching categories with pagination."""
        # Use a common word that might appear in multiple categories
        search_term = "Category"  # This should match multiple categories from test data
        
        response = client.get(f"{api_v1_prefix}/search/categories?q={search_term}&skip=0&limit=2", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]
        assert isinstance(data, list)
        assert len(data) <= 2

    def test_search_categories_unauthorized(self, client: TestClient, api_v1_prefix: str):
        """Test searching categories without authentication."""
        response = client.get(f"{api_v1_prefix}/search/categories?q=test")
        
        assert response.status_code == 403

    def test_search_all_success(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_book: Book, test_author: Author, test_category: Category):
        """Test searching across all entities."""
        # Use a general search term that might match different entities
        search_term = "test"
        
        response = client.get(f"{api_v1_prefix}/search/all?q={search_term}", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["success"] is True
        assert "message" in response_data
        data = response_data["data"]
        assert isinstance(data, dict)
        
        # Check response structure
        assert "books" in data
        assert "authors" in data
        assert "categories" in data
        assert "query" in data
        assert "results_count" in data
        
        # Check data types
        assert isinstance(data["books"], list)
        assert isinstance(data["authors"], list)
        assert isinstance(data["categories"], list)
        assert data["query"] == search_term
        
        # Check results count structure
        results_count = data["results_count"]
        assert "books" in results_count
        assert "authors" in results_count
        assert "categories" in results_count
        assert isinstance(results_count["books"], int)
        assert isinstance(results_count["authors"], int)
        assert isinstance(results_count["categories"], int)

    def test_search_all_with_specific_term(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_book: Book):
        """Test searching all with a specific term that should match a book."""
        search_term = test_book.title.split()[0]
        
        response = client.get(f"{api_v1_prefix}/search/all?q={search_term}", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]
        
        # Should find the book
        found_book = any(book["id"] == test_book.id for book in data["books"])
        assert found_book
        
        # Results count should be consistent
        assert data["results_count"]["books"] == len(data["books"])
        assert data["results_count"]["authors"] == len(data["authors"])
        assert data["results_count"]["categories"] == len(data["categories"])

    def test_search_all_no_results(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test searching all with no results."""
        search_term = "nonexistentanything"
        
        response = client.get(f"{api_v1_prefix}/search/all?q={search_term}", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]
        
        assert len(data["books"]) == 0
        assert len(data["authors"]) == 0
        assert len(data["categories"]) == 0
        assert data["results_count"]["books"] == 0
        assert data["results_count"]["authors"] == 0
        assert data["results_count"]["categories"] == 0

    def test_search_all_empty_query(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test searching all with empty query."""
        response = client.get(f"{api_v1_prefix}/search/all?q=", headers=auth_headers)
        
        assert response.status_code == 422

    def test_search_all_pagination(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, multiple_test_data: dict):
        """Test searching all with pagination."""
        search_term = "test"  # General term
        
        response = client.get(f"{api_v1_prefix}/search/all?q={search_term}&skip=0&limit=2", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]
        
        # Each category should have at most 2 results due to limit
        assert len(data["books"]) <= 2
        assert len(data["authors"]) <= 2
        assert len(data["categories"]) <= 2

    def test_search_all_unauthorized(self, client: TestClient, api_v1_prefix: str):
        """Test searching all without authentication."""
        response = client.get(f"{api_v1_prefix}/search/all?q=test")
        
        assert response.status_code == 403

    def test_search_special_characters(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test searching with special characters."""
        search_term = "test & search"
        
        response = client.get(f"{api_v1_prefix}/search/books?q={search_term}", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]
        assert isinstance(data, list)

    def test_search_unicode_characters(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test searching with unicode characters."""
        search_term = "tëst"
        
        response = client.get(f"{api_v1_prefix}/search/books?q={search_term}", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]
        assert isinstance(data, list)

    def test_search_very_long_query(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test searching with very long query."""
        search_term = "a" * 1000  # Very long search term
        
        response = client.get(f"{api_v1_prefix}/search/books?q={search_term}", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]
        assert isinstance(data, list)
        assert len(data) == 0  # Probably no results

    def test_search_case_insensitive(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_book: Book):
        """Test that search is case insensitive."""
        search_term_lower = test_book.title.lower()
        search_term_upper = test_book.title.upper()
        
        # Test lowercase
        response_lower = client.get(f"{api_v1_prefix}/search/books?q={search_term_lower}", headers=auth_headers)
        assert response_lower.status_code == 200
        data_lower = response_lower.json()["data"]
        
        # Test uppercase
        response_upper = client.get(f"{api_v1_prefix}/search/books?q={search_term_upper}", headers=auth_headers)
        assert response_upper.status_code == 200
        data_upper = response_upper.json()["data"]
        
        # Both should return the same book
        if data_lower and data_upper:
            found_book_lower = any(book["id"] == test_book.id for book in data_lower)
            found_book_upper = any(book["id"] == test_book.id for book in data_upper)
            assert found_book_lower == found_book_upper


@pytest.mark.asyncio
class TestSearchEndpointsAsync:
    """Test search endpoints with async client."""

    async def test_search_books_async(self, async_client: AsyncClient, api_v1_prefix: str, auth_headers: dict, test_book: Book):
        """Test searching books async."""
        search_term = test_book.title.split()[0]
        
        response = await async_client.get(f"{api_v1_prefix}/search/books?q={search_term}", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]
        assert isinstance(data, list)

    async def test_search_authors_async(self, async_client: AsyncClient, api_v1_prefix: str, auth_headers: dict, test_author: Author):
        """Test searching authors async."""
        search_term = test_author.name.split()[0]
        
        response = await async_client.get(f"{api_v1_prefix}/search/authors?q={search_term}", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]
        assert isinstance(data, list)

    async def test_search_categories_async(self, async_client: AsyncClient, api_v1_prefix: str, auth_headers: dict, test_category: Category):
        """Test searching categories async."""
        search_term = test_category.name.split()[0]
        
        response = await async_client.get(f"{api_v1_prefix}/search/categories?q={search_term}", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]
        assert isinstance(data, list)

    async def test_search_all_async(self, async_client: AsyncClient, api_v1_prefix: str, auth_headers: dict):
        """Test searching all async."""
        search_term = "test"
        
        response = await async_client.get(f"{api_v1_prefix}/search/all?q={search_term}", headers=auth_headers)
        
        assert response.status_code == 200
        response_data = response.json()
        data = response_data["data"]
        assert isinstance(data, dict)
        assert "books" in data
        assert "authors" in data
        assert "categories" in data
        assert "query" in data
        assert "results_count" in data 