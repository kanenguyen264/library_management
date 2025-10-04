"""
Test author management endpoints.
"""
import pytest
from app.crud.author import crud_author
from app.models.author import Author
from app.schemas.author import AuthorCreate
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.orm import Session


class TestAuthorEndpoints:
    """Test author management API endpoints."""

    def test_read_authors_success(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_author: Author):
        """Test reading authors list."""
        response = client.get(f"{api_v1_prefix}/authors/", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) > 0
        
        # Check author data structure
        author_data = data["data"][0]
        assert "id" in author_data
        assert "name" in author_data
        assert "bio" in author_data
        assert "nationality" in author_data
        assert "website" in author_data
        assert "created_at" in author_data

    def test_read_authors_unauthorized(self, client: TestClient, api_v1_prefix: str):
        """Test reading authors without authentication."""
        response = client.get(f"{api_v1_prefix}/authors/")
        
        assert response.status_code == 403

    def test_read_authors_pagination(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, db_session: Session):
        """Test reading authors with pagination."""
        # Create multiple authors
        for i in range(5):
            author_data = {
                "name": f"Author {i}",
                "bio": f"Biography of Author {i}",
                "nationality": f"Country {i}",
            }
            author_in = AuthorCreate(**author_data)
            crud_author.create(db_session, obj_in=author_in)
        
        # Test pagination
        response = client.get(f"{api_v1_prefix}/authors/?skip=0&limit=3", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) <= 3

    def test_create_author_admin(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test creating author as admin."""
        author_data = {
            "name": "George R.R. Martin",
            "bio": "American novelist and short story writer",
            "nationality": "American",
            "website": "https://www.georgerrmartin.com",
        }
        
        response = client.post(f"{api_v1_prefix}/authors/", json=author_data, headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["name"] == author_data["name"]
        assert data["data"]["bio"] == author_data["bio"]
        assert data["data"]["nationality"] == author_data["nationality"]
        assert data["data"]["website"] == author_data["website"]
        assert "id" in data["data"]
        assert "created_at" in data["data"]

    def test_create_author_non_admin(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test creating author as non-admin user."""
        author_data = {
            "name": "Stephen King",
            "bio": "American author of horror novels",
            "nationality": "American",
        }
        
        response = client.post(f"{api_v1_prefix}/authors/", json=author_data, headers=auth_headers)
        
        assert response.status_code == 403

    def test_create_author_missing_name(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test creating author without required name field."""
        author_data = {
            "bio": "Biography without name",
            "nationality": "Unknown",
        }
        
        response = client.post(f"{api_v1_prefix}/authors/", json=author_data, headers=admin_headers)
        
        assert response.status_code == 422

    def test_read_author_by_id_success(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_author: Author):
        """Test reading author by ID."""
        response = client.get(f"{api_v1_prefix}/authors/{test_author.id}", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["id"] == test_author.id
        assert data["data"]["name"] == test_author.name
        assert data["data"]["bio"] == test_author.bio
        assert data["data"]["nationality"] == test_author.nationality

    def test_read_author_by_id_not_found(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test reading non-existent author by ID."""
        response = client.get(f"{api_v1_prefix}/authors/99999", headers=auth_headers)
        
        assert response.status_code == 404

    def test_read_author_by_id_unauthorized(self, client: TestClient, api_v1_prefix: str, test_author: Author):
        """Test reading author by ID without authentication."""
        response = client.get(f"{api_v1_prefix}/authors/{test_author.id}")
        
        assert response.status_code == 403

    def test_update_author_admin(self, client: TestClient, api_v1_prefix: str, admin_headers: dict, test_author: Author):
        """Test updating author as admin."""
        update_data = {
            "name": "Updated Author Name",
            "bio": "Updated biography",
            "nationality": "Updated Nationality",
        }
        
        response = client.put(f"{api_v1_prefix}/authors/{test_author.id}", json=update_data, headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["name"] == update_data["name"]
        assert data["data"]["bio"] == update_data["bio"]
        assert data["data"]["nationality"] == update_data["nationality"]

    def test_update_author_non_admin(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_author: Author):
        """Test updating author as non-admin user."""
        update_data = {
            "name": "Unauthorized Update",
        }
        
        response = client.put(f"{api_v1_prefix}/authors/{test_author.id}", json=update_data, headers=auth_headers)
        
        assert response.status_code == 403

    def test_update_author_not_found(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test updating non-existent author."""
        update_data = {
            "name": "Updated Name",
        }
        
        response = client.put(f"{api_v1_prefix}/authors/99999", json=update_data, headers=admin_headers)
        
        assert response.status_code == 404

    def test_delete_author_admin(self, client: TestClient, api_v1_prefix: str, admin_headers: dict, db_session: Session):
        """Test deleting author as admin."""
        # Create author to delete
        author_data = {
            "name": "To Delete Author",
            "bio": "Author to be deleted",
            "nationality": "Unknown",
        }
        author_in = AuthorCreate(**author_data)
        author = crud_author.create(db_session, obj_in=author_in)
        
        response = client.delete(f"{api_v1_prefix}/authors/{author.id}", headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data

    def test_delete_author_non_admin(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_author: Author):
        """Test deleting author as non-admin user."""
        response = client.delete(f"{api_v1_prefix}/authors/{test_author.id}", headers=auth_headers)
        
        assert response.status_code == 403

    def test_delete_author_not_found(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test deleting non-existent author."""
        response = client.delete(f"{api_v1_prefix}/authors/99999", headers=admin_headers)
        
        assert response.status_code == 404

    def test_search_authors_success(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_author: Author):
        """Test searching authors by name."""
        search_term = test_author.name.split()[0]  # Search by first part of name
        
        response = client.get(f"{api_v1_prefix}/authors/search/?q={search_term}", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) > 0
        
        # Check if search result contains the author
        found_author = any(author["id"] == test_author.id for author in data["data"])
        assert found_author

    def test_search_authors_no_results(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test searching authors with no results."""
        response = client.get(f"{api_v1_prefix}/authors/search/?q=nonexistentauthor", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 0

    def test_search_authors_empty_query(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test searching authors with empty query."""
        response = client.get(f"{api_v1_prefix}/authors/search/?q=", headers=auth_headers)
        
        assert response.status_code == 422

    def test_search_authors_pagination(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, db_session: Session):
        """Test searching authors with pagination."""
        # Create multiple authors with similar names
        for i in range(5):
            author_data = {
                "name": f"SearchAuthor {i}",
                "bio": f"Biography of SearchAuthor {i}",
            }
            author_in = AuthorCreate(**author_data)
            crud_author.create(db_session, obj_in=author_in)
        
        # Search with pagination
        response = client.get(f"{api_v1_prefix}/authors/search/?q=SearchAuthor&skip=0&limit=3", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) <= 3

    def test_search_authors_unauthorized(self, client: TestClient, api_v1_prefix: str):
        """Test searching authors without authentication."""
        response = client.get(f"{api_v1_prefix}/authors/search/?q=test")
        
        assert response.status_code == 403


class TestAuthorCRUD:
    """Test author CRUD operations."""

    def test_create_author_crud(self, db_session: Session):
        """Test creating author through CRUD."""
        author_data = {
            "name": "CRUD Author",
            "bio": "Author created through CRUD",
            "nationality": "Test Country",
            "website": "https://example.com",
        }
        author_in = AuthorCreate(**author_data)
        author = crud_author.create(db_session, obj_in=author_in)
        
        assert author.name == author_data["name"]
        assert author.bio == author_data["bio"]
        assert author.nationality == author_data["nationality"]
        assert author.website == author_data["website"]
        assert author.id is not None

    def test_get_author_by_name(self, db_session: Session, test_author: Author):
        """Test getting author by name."""
        author = crud_author.get_by_name(db_session, name=test_author.name)
        
        assert author is not None
        assert author.name == test_author.name
        assert author.id == test_author.id

    def test_get_author_by_name_not_found(self, db_session: Session):
        """Test getting author by non-existent name."""
        author = crud_author.get_by_name(db_session, name="Nonexistent Author")
        
        assert author is None

    def test_search_authors_by_name(self, db_session: Session, test_author: Author):
        """Test searching authors by name."""
        search_term = test_author.name.split()[0]
        authors = crud_author.search_by_name(db_session, name=search_term)
        
        assert isinstance(authors, list)
        assert len(authors) > 0
        found_author = any(author.id == test_author.id for author in authors)
        assert found_author

    def test_search_authors_by_name_no_results(self, db_session: Session):
        """Test searching authors with no results."""
        authors = crud_author.search_by_name(db_session, name="NonexistentAuthor")
        
        assert isinstance(authors, list)
        assert len(authors) == 0

    def test_get_authors_by_nationality(self, db_session: Session):
        """Test getting authors by nationality."""
        # Create authors with same nationality
        nationality = "Test Country"
        for i in range(3):
            author_data = {
                "name": f"Author {i}",
                "bio": f"Biography {i}",
                "nationality": nationality,
            }
            author_in = AuthorCreate(**author_data)
            crud_author.create(db_session, obj_in=author_in)
        
        authors = crud_author.get_by_nationality(db_session, nationality=nationality)
        
        assert isinstance(authors, list)
        assert len(authors) >= 3
        for author in authors:
            assert author.nationality == nationality

    def test_get_authors_by_nationality_no_results(self, db_session: Session):
        """Test getting authors by non-existent nationality."""
        authors = crud_author.get_by_nationality(db_session, nationality="Nonexistent Country")
        
        assert isinstance(authors, list)
        assert len(authors) == 0

    def test_update_author_crud(self, db_session: Session, test_author: Author):
        """Test updating author through CRUD."""
        update_data = {
            "bio": "Updated biography through CRUD",
            "website": "https://updated.com",
        }
        
        updated_author = crud_author.update(db_session, db_obj=test_author, obj_in=update_data)
        
        assert updated_author.bio == update_data["bio"]
        assert updated_author.website == update_data["website"]
        assert updated_author.name == test_author.name  # Unchanged
        assert updated_author.nationality == test_author.nationality  # Unchanged

    def test_delete_author_crud(self, db_session: Session):
        """Test deleting author through CRUD."""
        # Create author to delete
        author_data = {
            "name": "Author to Delete",
            "bio": "This author will be deleted",
        }
        author_in = AuthorCreate(**author_data)
        author = crud_author.create(db_session, obj_in=author_in)
        author_id = author.id
        
        # Delete author
        deleted_author = crud_author.remove(db_session, id=author_id)
        
        assert deleted_author.id == author_id
        assert deleted_author.name == author.name
        
        # Verify author is deleted
        retrieved_author = crud_author.get(db_session, id=author_id)
        assert retrieved_author is None

    def test_get_multi_authors_crud(self, db_session: Session):
        """Test getting multiple authors through CRUD."""
        # Create multiple authors
        for i in range(5):
            author_data = {
                "name": f"Multi Author {i}",
                "bio": f"Biography {i}",
            }
            author_in = AuthorCreate(**author_data)
            crud_author.create(db_session, obj_in=author_in)
        
        authors = crud_author.get_multi(db_session, skip=0, limit=3)
        
        assert isinstance(authors, list)
        assert len(authors) <= 3

    def test_count_authors_crud(self, db_session: Session):
        """Test counting authors through CRUD."""
        # Create multiple authors
        initial_count = crud_author.count(db_session)
        
        for i in range(3):
            author_data = {
                "name": f"Count Author {i}",
                "bio": f"Biography {i}",
            }
            author_in = AuthorCreate(**author_data)
            crud_author.create(db_session, obj_in=author_in)
        
        final_count = crud_author.count(db_session)
        
        assert final_count == initial_count + 3


@pytest.mark.asyncio
class TestAuthorEndpointsAsync:
    """Test author endpoints with async client."""

    async def test_read_authors_async(self, async_client: AsyncClient, api_v1_prefix: str, auth_headers: dict):
        """Test reading authors list async."""
        response = await async_client.get(f"{api_v1_prefix}/authors/", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)

    async def test_create_author_async(self, async_client: AsyncClient, api_v1_prefix: str, admin_headers: dict):
        """Test creating author async."""
        author_data = {
            "name": "Async Author",
            "bio": "Author created asynchronously",
            "nationality": "Async Country",
        }
        
        response = await async_client.post(f"{api_v1_prefix}/authors/", json=author_data, headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["name"] == author_data["name"]

    async def test_search_authors_async(self, async_client: AsyncClient, api_v1_prefix: str, auth_headers: dict, test_author: Author):
        """Test searching authors async."""
        search_term = test_author.name.split()[0]
        
        response = await async_client.get(f"{api_v1_prefix}/authors/search?q={search_term}", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list) 