"""
Test user management endpoints.
"""
import pytest
from app.crud.user import crud_user
from app.models.user import User
from app.schemas.user import UserCreate
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.orm import Session


class TestUserEndpoints:
    """Test user management API endpoints."""

    def test_read_users_admin_only(self, client: TestClient, api_v1_prefix: str, admin_headers: dict, test_user: User):
        """Test reading users list (admin only)."""
        response = client.get(f"{api_v1_prefix}/users/", headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) > 0
        
        # Check user data structure
        user_data = data["data"][0]
        assert "id" in user_data
        assert "email" in user_data
        assert "username" in user_data
        assert "full_name" in user_data
        assert "is_active" in user_data
        assert "is_admin" in user_data
        assert "created_at" in user_data

    def test_read_users_non_admin(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test reading users as non-admin user."""
        response = client.get(f"{api_v1_prefix}/users/", headers=auth_headers)
        
        assert response.status_code == 403

    def test_read_users_unauthorized(self, client: TestClient, api_v1_prefix: str):
        """Test reading users without authentication."""
        response = client.get(f"{api_v1_prefix}/users/")
        
        assert response.status_code == 403

    def test_read_users_pagination(self, client: TestClient, api_v1_prefix: str, admin_headers: dict, db_session: Session):
        """Test reading users with pagination."""
        # Create multiple users
        for i in range(5):
            user_data = {
                "email": f"user{i}@example.com",
                "username": f"user{i}",
                "password": "testpassword123",
                "full_name": f"User {i}",
            }
            user_in = UserCreate(**user_data)
            crud_user.create(db_session, obj_in=user_in)
        
        # Test pagination
        response = client.get(f"{api_v1_prefix}/users/?skip=0&limit=3", headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) <= 3

    def test_create_user_admin(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test creating user as admin."""
        user_data = {
            "email": "newuser@example.com",
            "username": "newuser",
            "password": "newpassword123",
            "full_name": "New User",
            "is_admin": False,
        }
        
        response = client.post(f"{api_v1_prefix}/users/", json=user_data, headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["email"] == user_data["email"]
        assert data["data"]["username"] == user_data["username"]
        assert data["data"]["full_name"] == user_data["full_name"]
        assert data["data"]["is_admin"] == user_data["is_admin"]
        assert "id" in data["data"]
        assert "created_at" in data["data"]
        # Password should not be returned
        assert "password" not in data["data"]

    def test_create_user_non_admin(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test creating user as non-admin."""
        user_data = {
            "email": "unauthorized@example.com",
            "username": "unauthorized",
            "password": "password123",
            "full_name": "Unauthorized User",
        }
        
        response = client.post(f"{api_v1_prefix}/users/", json=user_data, headers=auth_headers)
        
        assert response.status_code == 403

    def test_create_user_duplicate_email(self, client: TestClient, api_v1_prefix: str, admin_headers: dict, test_user: User):
        """Test creating user with duplicate email."""
        user_data = {
            "email": test_user.email,
            "username": "different_username",
            "password": "password123",
            "full_name": "Duplicate Email User",
        }
        
        response = client.post(f"{api_v1_prefix}/users/", json=user_data, headers=admin_headers)
        
        assert response.status_code == 400

    def test_read_user_by_id_admin(self, client: TestClient, api_v1_prefix: str, admin_headers: dict, test_user: User):
        """Test reading user by ID as admin."""
        response = client.get(f"{api_v1_prefix}/users/{test_user.id}", headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["id"] == test_user.id
        assert data["data"]["email"] == test_user.email
        assert data["data"]["username"] == test_user.username
        assert data["data"]["full_name"] == test_user.full_name

    def test_read_user_by_id_not_found(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test reading non-existent user by ID."""
        response = client.get(f"{api_v1_prefix}/users/99999", headers=admin_headers)
        
        assert response.status_code == 404

    def test_read_user_by_id_self(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_user: User):
        """Test reading own user profile by ID."""
        response = client.get(f"{api_v1_prefix}/users/{test_user.id}", headers=auth_headers)
        
        # Users should be able to read their own profile
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["id"] == test_user.id

    def test_update_user_admin(self, client: TestClient, api_v1_prefix: str, admin_headers: dict, test_user: User):
        """Test updating user as admin."""
        update_data = {
            "full_name": "Updated Full Name",
            "bio": "Updated bio information",
            "is_active": False,
        }
        
        response = client.put(f"{api_v1_prefix}/users/{test_user.id}", json=update_data, headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["full_name"] == update_data["full_name"]
        assert data["data"]["bio"] == update_data["bio"]
        assert data["data"]["is_active"] == update_data["is_active"]

    def test_update_user_non_admin(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_user: User):
        """Test updating user as non-admin."""
        update_data = {
            "full_name": "Unauthorized Update",
        }
        
        response = client.put(f"{api_v1_prefix}/users/{test_user.id}", json=update_data, headers=auth_headers)
        
        assert response.status_code == 403

    def test_update_user_not_found(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test updating non-existent user."""
        update_data = {
            "full_name": "Non-existent User",
        }
        
        response = client.put(f"{api_v1_prefix}/users/99999", json=update_data, headers=admin_headers)
        
        assert response.status_code == 404

    def test_delete_user_admin(self, client: TestClient, api_v1_prefix: str, admin_headers: dict, db_session: Session):
        """Test deleting user as admin."""
        # Create user to delete
        user_data = {
            "email": "todelete@example.com",
            "username": "todelete",
            "password": "password123",
            "full_name": "To Delete User",
        }
        user_in = UserCreate(**user_data)
        user = crud_user.create(db_session, obj_in=user_in)
        
        response = client.delete(f"{api_v1_prefix}/users/{user.id}", headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data

    def test_delete_user_non_admin(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_user: User):
        """Test deleting user as non-admin."""
        response = client.delete(f"{api_v1_prefix}/users/{test_user.id}", headers=auth_headers)
        
        assert response.status_code == 403

    def test_delete_user_not_found(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test deleting non-existent user."""
        response = client.delete(f"{api_v1_prefix}/users/99999", headers=admin_headers)
        
        assert response.status_code == 404


class TestUserCRUD:
    """Test user CRUD operations."""

    def test_create_user_crud(self, db_session: Session):
        """Test creating user through CRUD."""
        user_data = {
            "email": "crud@example.com",
            "username": "cruduser",
            "full_name": "CRUD User",
            "password": "password123",
        }
        user_in = UserCreate(**user_data)
        user = crud_user.create(db_session, obj_in=user_in)
        
        assert user.email == user_data["email"]
        assert user.username == user_data["username"]
        assert user.full_name == user_data["full_name"]
        assert user.is_active is True
        assert user.is_admin is False
        assert user.hashed_password != user_data["password"]  # Should be hashed

    def test_get_user_by_email(self, db_session: Session, test_user: User):
        """Test getting user by email."""
        user = crud_user.get_by_email(db_session, email=test_user.email)
        
        assert user is not None
        assert user.email == test_user.email
        assert user.id == test_user.id

    def test_get_user_by_username(self, db_session: Session, test_user: User):
        """Test getting user by username."""
        user = crud_user.get_by_username(db_session, username=test_user.username)
        
        assert user is not None
        assert user.username == test_user.username
        assert user.id == test_user.id

    def test_get_user_by_email_not_found(self, db_session: Session):
        """Test getting user by non-existent email."""
        user = crud_user.get_by_email(db_session, email="nonexistent@example.com")
        
        assert user is None

    def test_get_user_by_username_not_found(self, db_session: Session):
        """Test getting user by non-existent username."""
        user = crud_user.get_by_username(db_session, username="nonexistent")
        
        assert user is None

    def test_authenticate_user_success(self, db_session: Session, test_user: User):
        """Test user authentication success."""
        user = crud_user.authenticate(db_session, email=test_user.email, password="testpassword123")
        
        assert user is not None
        assert user.email == test_user.email

    def test_authenticate_user_wrong_password(self, db_session: Session, test_user: User):
        """Test user authentication with wrong password."""
        user = crud_user.authenticate(db_session, email=test_user.email, password="wrongpassword")
        
        assert user is None

    def test_authenticate_user_wrong_email(self, db_session: Session):
        """Test user authentication with wrong email."""
        user = crud_user.authenticate(db_session, email="wrong@example.com", password="password")
        
        assert user is None

    def test_is_active_user(self, test_user: User):
        """Test checking if user is active."""
        assert crud_user.is_active(test_user) is True

    def test_is_admin_user(self, test_admin_user: User):
        """Test checking if user is admin."""
        assert crud_user.is_admin(test_admin_user) is True

    def test_is_admin_regular_user(self, test_user: User):
        """Test checking if regular user is admin."""
        assert crud_user.is_admin(test_user) is False


@pytest.mark.asyncio
class TestUserEndpointsAsync:
    """Test user endpoints with async client."""

    async def test_read_users_async(self, async_client: AsyncClient, api_v1_prefix: str, admin_headers: dict):
        """Test reading users list async."""
        response = await async_client.get(f"{api_v1_prefix}/users/", headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)

    async def test_create_user_async(self, async_client: AsyncClient, api_v1_prefix: str, admin_headers: dict):
        """Test creating user async."""
        user_data = {
            "email": "async_user@example.com",
            "username": "async_user",
            "full_name": "Async User",
            "password": "password123",
        }
        
        response = await async_client.post(f"{api_v1_prefix}/users/", json=user_data, headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["email"] == user_data["email"] 