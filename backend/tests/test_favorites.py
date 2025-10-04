from app.crud.favorite import crud_favorite
from app.schemas.favorite import FavoriteCreate
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


class TestFavorites:
    """Test cases for favorites functionality"""

    def test_create_favorite(self, client: TestClient, db_session: Session, auth_headers: dict, test_book, test_user):
        """Test creating a favorite"""
        favorite_data = {
            "book_id": test_book.id,
            "user_id": test_user.id  # Include user_id as required by schema
        }
        response = client.post(
            "/api/v1/favorites/",
            json=favorite_data,
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["book_id"] == test_book.id
        assert "id" in data["data"]
        assert "created_at" in data["data"]

    def test_create_favorite_duplicate(self, client: TestClient, db_session: Session, auth_headers: dict, test_book, test_user):
        """Test creating duplicate favorite"""
        # Create favorite first
        favorite_data = {
            "book_id": test_book.id,
            "user_id": test_user.id
        }
        favorite_in = FavoriteCreate(**favorite_data)
        crud_favorite.create(db_session, obj_in=favorite_in)
        
        # Try to create duplicate
        favorite_request = {
            "book_id": test_book.id,
            "user_id": test_user.id
        }
        response = client.post(
            "/api/v1/favorites/",
            json=favorite_request,
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_remove_favorite_by_book(self, client: TestClient, db_session: Session, auth_headers: dict, test_book, test_user):
        """Test removing favorite by book ID"""
        # Create favorite first
        favorite_data = {
            "book_id": test_book.id,
            "user_id": test_user.id
        }
        favorite_in = FavoriteCreate(**favorite_data)
        crud_favorite.create(db_session, obj_in=favorite_in)
        
        response = client.delete(f"/api/v1/favorites/book/{test_book.id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data

    def test_remove_nonexistent_favorite(self, client: TestClient, auth_headers: dict):
        """Test removing non-existent favorite"""
        response = client.delete("/api/v1/favorites/book/99999", headers=auth_headers)
        assert response.status_code == 404

    def test_favorites_require_auth(self, client: TestClient, test_book, test_user):
        """Test that favorites endpoints require authentication"""
        # Test create favorite without auth
        favorite_data = {"book_id": test_book.id, "user_id": test_user.id}
        response = client.post("/api/v1/favorites/", json=favorite_data)
        assert response.status_code == 403
        
        # Test get favorites without auth
        response = client.get("/api/v1/favorites/")
        assert response.status_code == 403
        
        # Test delete favorite without auth
        response = client.delete(f"/api/v1/favorites/book/{test_book.id}")
        assert response.status_code == 403


class TestFavoriteCRUD:
    """Test favorite CRUD operations"""

    def test_create_favorite_crud(self, db_session: Session, test_user, test_book):
        """Test creating favorite via CRUD"""
        favorite_data = {"user_id": test_user.id, "book_id": test_book.id}
        favorite_in = FavoriteCreate(**favorite_data)
        favorite = crud_favorite.create(db_session, obj_in=favorite_in)
        
        assert favorite.user_id == test_user.id
        assert favorite.book_id == test_book.id
        assert favorite.id is not None

    def test_get_by_user_and_book(self, db_session: Session, test_user, test_book):
        """Test getting favorite by user and book"""
        # Create favorite first
        favorite_data = {"user_id": test_user.id, "book_id": test_book.id}
        favorite_in = FavoriteCreate(**favorite_data)
        created_favorite = crud_favorite.create(db_session, obj_in=favorite_in)
        
        # Get it back
        found_favorite = crud_favorite.get_by_user_and_book(
            db_session, user_id=test_user.id, book_id=test_book.id
        )
        
        assert found_favorite is not None
        assert found_favorite.id == created_favorite.id

    def test_get_by_user(self, db_session: Session, test_user, test_book):
        """Test getting favorites by user"""
        # Create favorite first
        favorite_data = {"user_id": test_user.id, "book_id": test_book.id}
        favorite_in = FavoriteCreate(**favorite_data)
        crud_favorite.create(db_session, obj_in=favorite_in)
        
        # Get user's favorites
        favorites = crud_favorite.get_by_user(db_session, user_id=test_user.id)
        
        assert len(favorites) > 0
        assert favorites[0].user_id == test_user.id

    def test_get_user_favorites_count(self, db_session: Session, test_user, test_book):
        """Test getting user favorites count"""
        # Initially 0
        count = crud_favorite.get_user_favorites_count(db_session, user_id=test_user.id)
        assert count == 0
        
        # Create favorite
        favorite_data = {"user_id": test_user.id, "book_id": test_book.id}
        favorite_in = FavoriteCreate(**favorite_data)
        crud_favorite.create(db_session, obj_in=favorite_in)
        
        # Now should be 1
        count = crud_favorite.get_user_favorites_count(db_session, user_id=test_user.id)
        assert count == 1 