"""
Test authentication endpoints and functionality.
"""
import pytest
from app.core.auth import create_access_token, verify_password, verify_token
from app.crud.user import crud_user
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.token_service import token_service
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.orm import Session


class TestAuthEndpoints:
    """Test authentication API endpoints."""

    def test_register_user_success(self, client: TestClient, api_v1_prefix: str):
        """Test successful user registration."""
        user_data = {
            "email": "newuser@example.com",
            "username": "newuser",
            "full_name": "New User",
            "password": "newpassword123",
        }

        response = client.post(f"{api_v1_prefix}/auth/register", json=user_data)

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Registration successful"
        assert data["data"]["email"] == user_data["email"]
        assert data["data"]["username"] == user_data["username"]
        assert data["data"]["full_name"] == user_data["full_name"]
        assert "password" not in data["data"]  # Password should not be returned
        assert "id" in data["data"]

    def test_register_user_duplicate_email(self, client: TestClient, api_v1_prefix: str, test_user: User):
        """Test registration with duplicate email."""
        user_data = {
            "email": test_user.email,
            "username": "differentuser",
            "full_name": "Different User",
            "password": "password123",
        }

        response = client.post(f"{api_v1_prefix}/auth/register", json=user_data)

        assert response.status_code == 400
        assert "already registered" in response.json()["detail"].lower()

    def test_register_user_duplicate_username(self, client: TestClient, api_v1_prefix: str, test_user: User):
        """Test registration with duplicate username."""
        user_data = {
            "email": "different@example.com",
            "username": test_user.username,
            "full_name": "Different User",
            "password": "password123",
        }

        response = client.post(f"{api_v1_prefix}/auth/register", json=user_data)

        assert response.status_code == 400
        assert "already registered" in response.json()["detail"].lower()

    def test_register_user_invalid_email(self, client: TestClient, api_v1_prefix: str):
        """Test registration with invalid email format."""
        user_data = {
            "email": "invalid-email",
            "username": "testuser",
            "full_name": "Test User",
            "password": "password123",
        }

        response = client.post(f"{api_v1_prefix}/auth/register", json=user_data)

        assert response.status_code == 422

    def test_register_user_missing_fields(self, client: TestClient, api_v1_prefix: str):
        """Test registration with missing required fields."""
        user_data = {
            "email": "test@example.com",
            # Missing username, full_name, password
        }

        response = client.post(f"{api_v1_prefix}/auth/register", json=user_data)

        assert response.status_code == 422

    def test_login_success(self, client: TestClient, api_v1_prefix: str, test_user: User):
        """Test successful login."""
        login_data = {
            "username": test_user.email,  # OAuth2 uses username field for email
            "password": "testpassword123",
        }

        response = client.post(f"{api_v1_prefix}/auth/login", data=login_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert "access_token" in data["data"]
        assert data["data"]["token_type"] == "bearer"
        assert len(data["data"]["access_token"]) > 0

    def test_login_json_success(self, client: TestClient, api_v1_prefix: str, test_user: User):
        """Test successful JSON login."""
        login_data = {
            "username": test_user.email,  # Use email as username
            "password": "testpassword123",
        }

        response = client.post(f"{api_v1_prefix}/auth/login-json", json=login_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert "data" in data
        assert "access_token" in data["data"]
        assert data["data"]["token_type"] == "bearer"
        assert len(data["data"]["access_token"]) > 0

    def test_login_json_invalid_email(self, client: TestClient, api_v1_prefix: str):
        """Test JSON login with invalid email."""
        login_data = {
            "username": "nonexistent@example.com",  # Use email as username
            "password": "password123",
        }

        response = client.post(f"{api_v1_prefix}/auth/login-json", json=login_data)

        assert response.status_code == 400
        assert "invalid credentials" in response.json()["detail"].lower()

    def test_login_json_invalid_password(self, client: TestClient, api_v1_prefix: str, test_user: User):
        """Test JSON login with invalid password."""
        login_data = {
            "username": test_user.email,  # Use email as username
            "password": "wrongpassword",
        }

        response = client.post(f"{api_v1_prefix}/auth/login-json", json=login_data)

        assert response.status_code == 400
        assert "invalid credentials" in response.json()["detail"].lower()

    def test_login_json_inactive_user(self, client: TestClient, api_v1_prefix: str, db_session: Session):
        """Test JSON login with inactive user."""
        # Create inactive user
        inactive_user_data = {
            "email": "inactive@example.com",
            "username": "inactive",
            "full_name": "Inactive User",
            "password": "password123",
            "is_active": False,
        }
        user_in = UserCreate(**inactive_user_data)
        crud_user.create(db_session, obj_in=user_in)

        login_data = {
            "username": "inactive@example.com",  # Use email as username
            "password": "password123",
        }

        response = client.post(f"{api_v1_prefix}/auth/login-json", json=login_data)

        assert response.status_code == 400
        assert "inactive user" in response.json()["detail"].lower()

    def test_login_invalid_email(self, client: TestClient, api_v1_prefix: str):
        """Test login with invalid email."""
        login_data = {
            "username": "nonexistent@example.com",
            "password": "password123",
        }

        response = client.post(f"{api_v1_prefix}/auth/login", data=login_data)

        assert response.status_code == 400
        assert "invalid credentials" in response.json()["detail"].lower()

    def test_login_invalid_password(self, client: TestClient, api_v1_prefix: str, test_user: User):
        """Test login with invalid password."""
        login_data = {
            "username": test_user.email,
            "password": "wrongpassword",
        }

        response = client.post(f"{api_v1_prefix}/auth/login", data=login_data)

        assert response.status_code == 400
        assert "invalid credentials" in response.json()["detail"].lower()

    def test_login_inactive_user(self, client: TestClient, api_v1_prefix: str, db_session: Session):
        """Test login with inactive user."""
        # Create inactive user
        inactive_user_data = {
            "email": "inactive@example.com",
            "username": "inactive",
            "full_name": "Inactive User",
            "password": "password123",
            "is_active": False,
        }
        user_in = UserCreate(**inactive_user_data)
        crud_user.create(db_session, obj_in=user_in)

        login_data = {
            "username": "inactive@example.com",
            "password": "password123",
        }

        response = client.post(f"{api_v1_prefix}/auth/login", data=login_data)

        assert response.status_code == 400
        assert "inactive user" in response.json()["detail"].lower()

    def test_forgot_password_success(self, client: TestClient, api_v1_prefix: str, test_user: User):
        """Test successful forgot password request."""
        forgot_data = {
            "email": test_user.email,
        }

        response = client.post(f"{api_v1_prefix}/auth/forgot-password", json=forgot_data)

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "password reset email sent successfully" in data["message"].lower()

    def test_forgot_password_nonexistent_email(self, client: TestClient, api_v1_prefix: str):
        """Test forgot password with nonexistent email."""
        forgot_data = {
            "email": "nonexistent@example.com",
        }

        response = client.post(f"{api_v1_prefix}/auth/forgot-password", json=forgot_data)

        # Should return success message for security (don't reveal if email exists)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "password reset email sent successfully" in data["message"].lower()

    def test_forgot_password_inactive_user(self, client: TestClient, api_v1_prefix: str, db_session: Session):
        """Test forgot password with inactive user."""
        # Create inactive user
        inactive_user_data = {
            "email": "inactive@example.com",
            "username": "inactive",
            "full_name": "Inactive User",
            "password": "password123",
            "is_active": False,
        }
        user_in = UserCreate(**inactive_user_data)
        crud_user.create(db_session, obj_in=user_in)

        forgot_data = {
            "email": "inactive@example.com",
        }

        response = client.post(f"{api_v1_prefix}/auth/forgot-password", json=forgot_data)

        # Should return success message for security (don't reveal user status)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "password reset email sent successfully" in data["message"].lower()

    def test_reset_password_success(self, client: TestClient, api_v1_prefix: str, test_user: User):
        """Test successful password reset."""
        # Create a valid reset token
        reset_token = token_service.create_password_reset_token(test_user.email)

        reset_data = {
            "token": reset_token,
            "new_password": "newpassword123",
        }

        response = client.post(f"{api_v1_prefix}/auth/reset-password", json=reset_data)

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "password reset successful" in data["message"].lower()

    def test_reset_password_invalid_token(self, client: TestClient, api_v1_prefix: str):
        """Test password reset with invalid token."""
        reset_data = {
            "token": "invalid_token",
            "new_password": "newpassword123",
        }

        response = client.post(f"{api_v1_prefix}/auth/reset-password", json=reset_data)

        assert response.status_code == 400
        assert "invalid token" in response.json()["detail"].lower()

    def test_reset_password_expired_token(self, client: TestClient, api_v1_prefix: str):
        """Test password reset with expired token."""
        # Create an expired token (manually create one with past expiry)
        from datetime import datetime, timedelta

        import jwt
        from app.core.config import settings

        expired_token = jwt.encode(
            {
                "sub": "test@example.com",
                "exp": datetime.utcnow() - timedelta(hours=1),  # Expired 1 hour ago
                "type": "password_reset"
            },
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM
        )

        reset_data = {
            "token": expired_token,
            "new_password": "newpassword123",
        }

        response = client.post(f"{api_v1_prefix}/auth/reset-password", json=reset_data)

        assert response.status_code == 400
        assert "invalid token" in response.json()["detail"].lower()

    def test_reset_password_nonexistent_user(self, client: TestClient, api_v1_prefix: str):
        """Test password reset for nonexistent user."""
        # Create token for nonexistent user
        reset_token = token_service.create_password_reset_token("nonexistent@example.com")

        reset_data = {
            "token": reset_token,
            "new_password": "newpassword123",
        }

        response = client.post(f"{api_v1_prefix}/auth/reset-password", json=reset_data)

        assert response.status_code == 404
        assert "user not found" in response.json()["detail"].lower()

    def test_change_password_success(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test successful password change."""
        change_data = {
            "current_password": "testpassword123",
            "new_password": "newpassword123",
        }

        response = client.post(f"{api_v1_prefix}/auth/change-password", json=change_data, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "password changed successfully" in data["message"].lower()

    def test_change_password_wrong_current_password(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test password change with wrong current password."""
        change_data = {
            "current_password": "wrongpassword",
            "new_password": "newpassword123",
        }

        response = client.post(f"{api_v1_prefix}/auth/change-password", json=change_data, headers=auth_headers)

        assert response.status_code == 400
        assert "incorrect password" in response.json()["detail"].lower()

    def test_change_password_unauthorized(self, client: TestClient, api_v1_prefix: str):
        """Test password change without authentication."""
        change_data = {
            "current_password": "testpassword123",
            "new_password": "newpassword123",
        }

        response = client.post(f"{api_v1_prefix}/auth/change-password", json=change_data)

        assert response.status_code == 403

    def test_test_token_valid(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test token validation with valid token."""
        response = client.post(f"{api_v1_prefix}/auth/test-token", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert "email" in data["data"]
        assert "username" in data["data"]

    def test_test_token_invalid(self, client: TestClient, api_v1_prefix: str):
        """Test token validation with invalid token."""
        headers = {"Authorization": "Bearer invalid_token"}
        response = client.post(f"{api_v1_prefix}/auth/test-token", headers=headers)

        assert response.status_code == 401

    def test_test_token_missing(self, client: TestClient, api_v1_prefix: str):
        """Test token validation without token."""
        response = client.post(f"{api_v1_prefix}/auth/test-token")

        assert response.status_code == 403

    def test_get_current_user_success(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test getting current user information."""
        response = client.get(f"{api_v1_prefix}/auth/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert "email" in data["data"]
        assert "username" in data["data"]

    def test_get_current_user_unauthorized(self, client: TestClient, api_v1_prefix: str):
        """Test getting current user without authentication."""
        response = client.get(f"{api_v1_prefix}/auth/me")

        assert response.status_code == 403


class TestAuthUtilities:
    """Test authentication utility functions."""

    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        from app.core.auth import get_password_hash

        password = "testpassword123"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password."""
        from app.core.auth import get_password_hash

        password = "testpassword123"
        wrong_password = "wrongpassword"
        hashed = get_password_hash(password)

        assert verify_password(wrong_password, hashed) is False

    def test_create_access_token(self):
        """Test creating access token."""
        user_id = 123
        token = create_access_token(user_id)

        assert token is not None
        assert isinstance(token, str)

    def test_verify_token_valid(self):
        """Test token verification with valid token."""
        user_id = 123
        token = create_access_token(user_id)

        token_data = verify_token(token)
        assert token_data is not None
        assert token_data.user_id == user_id

    def test_verify_token_invalid(self):
        """Test token verification with invalid token."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            verify_token("invalid_token")

        assert exc_info.value.status_code == 401
        assert "could not validate credentials" in exc_info.value.detail.lower()

    def test_authenticate_user_success(self, db_session: Session, test_user: User):
        """Test user authentication with correct credentials."""
        from app.core.auth import authenticate_user

        user = authenticate_user(db_session, test_user.email, "testpassword123")
        assert user is not None
        assert user.email == test_user.email

    def test_authenticate_user_wrong_email(self, db_session: Session):
        """Test user authentication with wrong email."""
        from app.core.auth import authenticate_user

        user = authenticate_user(db_session, "wrong@example.com", "password123")
        assert user is None

    def test_authenticate_user_wrong_password(self, db_session: Session, test_user: User):
        """Test user authentication with wrong password."""
        from app.core.auth import authenticate_user

        user = authenticate_user(db_session, test_user.email, "wrongpassword")
        assert user is None


class TestTokenService:
    """Test token service functionality."""

    def test_create_password_reset_token(self):
        """Test password reset token creation."""
        email = "test@example.com"
        token = token_service.create_password_reset_token(email)

        assert isinstance(token, str)
        assert len(token) > 0

        # Verify token
        verified_email = token_service.verify_password_reset_token(token)
        assert verified_email == email

    def test_verify_password_reset_token_invalid(self):
        """Test password reset token verification with invalid token."""
        verified_email = token_service.verify_password_reset_token("invalid_token")
        assert verified_email is None

    def test_create_verification_token(self):
        """Test email verification token creation."""
        email = "test@example.com"
        token = token_service.create_verification_token(email)

        assert isinstance(token, str)
        assert len(token) > 0

        # Verify token
        verified_email = token_service.verify_verification_token(token)
        assert verified_email == email

    def test_verify_verification_token_invalid(self):
        """Test email verification token verification with invalid token."""
        verified_email = token_service.verify_verification_token("invalid_token")
        assert verified_email is None

    def test_generate_secure_token(self):
        """Test secure token generation."""
        token1 = token_service.generate_secure_token()
        token2 = token_service.generate_secure_token()

        assert isinstance(token1, str)
        assert isinstance(token2, str)
        assert len(token1) > 0
        assert len(token2) > 0
        assert token1 != token2  # Should be different


@pytest.mark.asyncio
class TestAuthAsync:
    """Test authentication endpoints asynchronously."""

    async def test_register_async(self, async_client: AsyncClient, api_v1_prefix: str):
        """Test async user registration."""
        user_data = {
            "email": "asyncuser@example.com",
            "username": "asyncuser",
            "full_name": "Async User",
            "password": "password123",
        }

        response = await async_client.post(f"{api_v1_prefix}/auth/register", json=user_data)

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["email"] == user_data["email"]
        assert data["data"]["username"] == user_data["username"]
        assert data["data"]["full_name"] == user_data["full_name"]

    async def test_login_async(self, async_client: AsyncClient, api_v1_prefix: str, test_user: User):
        """Test async user login."""
        login_data = {
            "username": test_user.email,
            "password": "testpassword123",
        }

        response = await async_client.post(f"{api_v1_prefix}/auth/login", data=login_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert "access_token" in data["data"]
        assert data["data"]["token_type"] == "bearer" 