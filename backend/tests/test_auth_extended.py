"""
Tests for extended authentication endpoints.
"""
from unittest.mock import patch

from app.crud.user import crud_user
from app.models.user import User
from app.schemas.user import UserCreate
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


class TestExtendedAuthEndpoints:
    """Test extended authentication endpoints."""

    def test_login_json_success(self, client: TestClient, api_v1_prefix: str, test_user: User):
        """Test successful JSON login."""
        login_data = {
            "username": test_user.email,
            "password": "testpassword123",
        }
        
        response = client.post(f"{api_v1_prefix}/auth/login-json", json=login_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert "access_token" in data["data"]
        assert data["data"]["token_type"] == "bearer"
        assert len(data["data"]["access_token"]) > 0

    def test_login_json_invalid_email(self, client: TestClient, api_v1_prefix: str):
        """Test JSON login with invalid email."""
        login_data = {
            "username": "nonexistent@example.com",
            "password": "password123",
        }
        
        response = client.post(f"{api_v1_prefix}/auth/login-json", json=login_data)
        
        assert response.status_code == 400
        assert "invalid credentials" in response.json()["detail"].lower()

    def test_login_json_invalid_password(self, client: TestClient, api_v1_prefix: str, test_user: User):
        """Test JSON login with invalid password."""
        login_data = {
            "username": test_user.email,
            "password": "wrongpassword",
        }
        
        response = client.post(f"{api_v1_prefix}/auth/login-json", json=login_data)
        
        assert response.status_code == 400
        assert "invalid credentials" in response.json()["detail"].lower()

    def test_login_json_inactive_user(self, client: TestClient, api_v1_prefix: str, db_session: Session):
        """Test JSON login with inactive user."""
        # Create inactive user
        inactive_user_data = {
            "email": "inactive_json@example.com",
            "username": "inactive_json",
            "full_name": "Inactive JSON User",
            "password": "password123",
            "is_active": False,
        }
        user_in = UserCreate(**inactive_user_data)
        crud_user.create(db_session, obj_in=user_in)
        
        login_data = {
            "username": "inactive_json@example.com",
            "password": "password123",
        }
        
        response = client.post(f"{api_v1_prefix}/auth/login-json", json=login_data)
        
        assert response.status_code == 400
        assert "inactive user" in response.json()["detail"].lower()

    @patch('app.services.email_service.email_service.send_password_reset_email')
    def test_forgot_password_success(self, mock_send_email, client: TestClient, api_v1_prefix: str, test_user: User):
        """Test successful forgot password request."""
        mock_send_email.return_value = True
        
        forgot_data = {
            "email": test_user.email,
        }
        
        response = client.post(f"{api_v1_prefix}/auth/forgot-password", json=forgot_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "password reset email sent successfully" in data["message"].lower()
        mock_send_email.assert_called_once()

    def test_forgot_password_nonexistent_email(self, client: TestClient, api_v1_prefix: str):
        """Test forgot password with nonexistent email."""
        forgot_data = {
            "email": "nonexistent@example.com",
        }
        
        response = client.post(f"{api_v1_prefix}/auth/forgot-password", json=forgot_data)
        
        # Should return same message for security
        assert response.status_code == 200
        data = response.json()
        assert "password reset email sent successfully" in data["message"].lower()

    def test_forgot_password_inactive_user(self, client: TestClient, api_v1_prefix: str, db_session: Session):
        """Test forgot password with inactive user."""
        # Create inactive user
        inactive_user_data = {
            "email": "inactive_forgot@example.com",
            "username": "inactive_forgot",
            "full_name": "Inactive Forgot User",
            "password": "password123",
            "is_active": False,
        }
        user_in = UserCreate(**inactive_user_data)
        crud_user.create(db_session, obj_in=user_in)
        
        forgot_data = {
            "email": "inactive_forgot@example.com",
        }
        
        response = client.post(f"{api_v1_prefix}/auth/forgot-password", json=forgot_data)
        
        # Should return same message for security
        assert response.status_code == 200
        data = response.json()
        assert "password reset email sent successfully" in data["message"].lower()

    @patch('app.services.token_service.token_service.verify_password_reset_token')
    def test_reset_password_success(self, mock_verify_token, client: TestClient, api_v1_prefix: str, test_user: User):
        """Test successful password reset."""
        mock_verify_token.return_value = test_user.email
        
        reset_data = {
            "token": "valid_reset_token",
            "new_password": "newpassword123",
        }
        
        response = client.post(f"{api_v1_prefix}/auth/reset-password", json=reset_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "password reset successful" in data["message"].lower()
        mock_verify_token.assert_called_once_with("valid_reset_token")

    @patch('app.services.token_service.token_service.verify_password_reset_token')
    def test_reset_password_invalid_token(self, mock_verify_token, client: TestClient, api_v1_prefix: str):
        """Test password reset with invalid token."""
        mock_verify_token.return_value = None
        
        reset_data = {
            "token": "invalid_token",
            "new_password": "newpassword123",
        }
        
        response = client.post(f"{api_v1_prefix}/auth/reset-password", json=reset_data)
        
        assert response.status_code == 400
        assert "invalid token" in response.json()["detail"].lower()

    @patch('app.services.token_service.token_service.verify_password_reset_token')
    def test_reset_password_nonexistent_user(self, mock_verify_token, client: TestClient, api_v1_prefix: str):
        """Test password reset with token for nonexistent user."""
        mock_verify_token.return_value = "nonexistent@example.com"
        
        reset_data = {
            "token": "valid_token_nonexistent_user",
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
        assert "password changed successfully" in data["message"].lower()

    def test_change_password_wrong_current(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
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


class TestTokenService:
    """Test token service functionality."""

    def test_create_password_reset_token(self):
        """Test password reset token creation."""
        from app.services.token_service import token_service
        
        email = "test@example.com"
        token = token_service.create_password_reset_token(email)
        
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_password_reset_token_valid(self):
        """Test verification of valid password reset token."""
        from app.services.token_service import token_service
        
        email = "test@example.com"
        token = token_service.create_password_reset_token(email)
        
        verified_email = token_service.verify_password_reset_token(token)
        assert verified_email == email

    def test_verify_password_reset_token_invalid(self):
        """Test verification of invalid password reset token."""
        from app.services.token_service import token_service
        
        verified_email = token_service.verify_password_reset_token("invalid_token")
        assert verified_email is None

    def test_create_verification_token(self):
        """Test email verification token creation."""
        from app.services.token_service import token_service
        
        email = "test@example.com"
        token = token_service.create_verification_token(email)
        
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_verification_token_valid(self):
        """Test verification of valid email verification token."""
        from app.services.token_service import token_service
        
        email = "test@example.com"
        token = token_service.create_verification_token(email)
        
        verified_email = token_service.verify_verification_token(token)
        assert verified_email == email

    def test_generate_secure_token(self):
        """Test secure token generation."""
        from app.services.token_service import token_service
        
        token = token_service.generate_secure_token()
        assert isinstance(token, str)
        assert len(token) > 0
        
        # Test with custom length
        custom_token = token_service.generate_secure_token(16)
        assert isinstance(custom_token, str)
        assert len(custom_token) > 0 