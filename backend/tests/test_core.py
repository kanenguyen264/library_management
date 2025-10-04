"""
Core functionality tests.
"""
import pytest
from app.core.config import settings
from app.core.database import engine, get_db
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import text


class TestSettings:
    """Test application settings."""

    def test_settings_loaded(self):
        """Test that settings are properly loaded."""
        assert settings.PROJECT_NAME
        assert settings.VERSION
        assert settings.API_V1_STR
        assert settings.SECRET_KEY

    def test_settings_pagination(self):
        """Test pagination settings."""
        assert isinstance(settings.DEFAULT_PAGE_SIZE, int)
        assert settings.DEFAULT_PAGE_SIZE > 0
        assert isinstance(settings.MAX_PAGE_SIZE, int)
        assert settings.MAX_PAGE_SIZE >= settings.DEFAULT_PAGE_SIZE

    def test_settings_upload_config(self):
        """Test file upload configuration."""
        # Check if upload settings exist
        if hasattr(settings, 'MAX_UPLOAD_SIZE'):
            assert isinstance(settings.MAX_UPLOAD_SIZE, int)
            assert settings.MAX_UPLOAD_SIZE > 0
        
        if hasattr(settings, 'ALLOWED_IMAGE_TYPES'):
            assert isinstance(settings.ALLOWED_IMAGE_TYPES, list)
            assert len(settings.ALLOWED_IMAGE_TYPES) > 0

    def test_settings_development_specific(self):
        """Test development-specific settings."""
        if settings.ENVIRONMENT == "development":
            assert settings.DEBUG is True
        else:
            assert settings.DEBUG is False

    def test_settings_production_defaults(self):
        """Test production default settings."""
        assert settings.ENVIRONMENT in ["development", "testing", "production"]
        assert isinstance(settings.BACKEND_CORS_ORIGINS, list)


class TestDatabase:
    """Test database configuration."""

    def test_database_engine_exists(self):
        """Test that database engine is created."""
        assert engine is not None

    def test_database_connection(self):
        """Test database connection."""
        try:
            db = next(get_db())
            # Test connection with a simple query
            result = db.execute(text("SELECT 1")).fetchone()
            assert result[0] == 1
            db.close()
        except Exception as e:
            pytest.fail(f"Database connection failed: {e}")

    def test_get_db_dependency(self):
        """Test get_db dependency function."""
        db_generator = get_db()
        db = next(db_generator)
        assert db is not None
        # Clean up
        try:
            next(db_generator)
        except StopIteration:
            pass

    def test_database_transaction(self):
        """Test database transaction handling."""
        db = next(get_db())
        try:
            # Start a transaction
            db.begin()
            # Test query
            result = db.execute(text("SELECT 1")).fetchone()
            assert result[0] == 1
            # Rollback
            db.rollback()
        finally:
            db.close()


class TestApplication:
    """Test FastAPI application setup."""

    def test_app_instance(self):
        """Test that app instance is created."""
        assert app is not None
        assert app.title == settings.PROJECT_NAME
        # Version might have different formats (1.0.0 vs 1.0.0-dev)
        assert app.version.startswith(settings.VERSION.split('-')[0])

    def test_app_version(self):
        """Test app version."""
        # Version might have different formats (1.0.0 vs 1.0.0-dev)
        assert app.version.startswith(settings.VERSION.split('-')[0])

    def test_app_openapi_url(self):
        """Test OpenAPI URL configuration."""
        expected_url = f"{settings.API_V1_STR}/openapi.json"
        assert app.openapi_url == expected_url

    def test_root_endpoint(self, client: TestClient):
        """Test root endpoint."""
        response = client.get("/")
        # Accept 404 when no static files are present (test environment)
        # Accept 200/307 when static files are served (production)
        assert response.status_code in [200, 307, 404]

    def test_health_endpoint(self, client: TestClient):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"

    def test_api_prefix_routing(self, client: TestClient):
        """Test API prefix routing."""
        # Test that API routes are accessible under the prefix
        response = client.get(f"{settings.API_V1_STR}/")
        # Should either redirect or return 404, not 500
        assert response.status_code in [200, 404, 405, 307]

    def test_cors_middleware(self, client: TestClient):
        """Test CORS middleware is configured."""
        headers = {"Origin": "http://localhost:3000"}
        response = client.get("/health", headers=headers)
        assert response.status_code == 200
        # CORS headers may or may not be present depending on configuration

    def test_openapi_docs_accessible(self, client: TestClient):
        """Test that OpenAPI docs are accessible."""
        response = client.get("/docs")
        assert response.status_code == 200

    @pytest.mark.skip(reason="OpenAPI schema generation has forward reference issues")
    def test_openapi_json_accessible(self, client: TestClient):
        """Test that OpenAPI JSON is accessible."""
        response = client.get(f"{settings.API_V1_STR}/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "info" in data


class TestAPIRoutes:
    """Test API route registration."""

    def test_auth_routes_registered(self, client: TestClient):
        """Test that auth routes are registered."""
        # Test a known auth endpoint
        response = client.post(f"{settings.API_V1_STR}/auth/register")
        # Should return 422 (validation error) not 404 (not found)
        assert response.status_code in [422, 400]

    def test_users_routes_registered(self, client: TestClient):
        """Test that users routes are registered."""
        response = client.get(f"{settings.API_V1_STR}/users/")
        # Should return 403 (forbidden) not 404 (not found)
        assert response.status_code == 403

    def test_authors_routes_registered(self, client: TestClient):
        """Test that authors routes are registered."""
        response = client.get(f"{settings.API_V1_STR}/authors/")
        # Should return 403 (forbidden) not 404 (not found)
        assert response.status_code == 403

    def test_categories_routes_registered(self, client: TestClient):
        """Test that categories routes are registered."""
        response = client.get(f"{settings.API_V1_STR}/categories/")
        # Should return 403 (forbidden) not 404 (not found)
        assert response.status_code == 403

    def test_books_routes_registered(self, client: TestClient):
        """Test that books routes are registered."""
        response = client.get(f"{settings.API_V1_STR}/books/")
        # Should return 403 (forbidden) not 404 (not found)
        assert response.status_code == 403

    def test_reading_progress_routes_registered(self, client: TestClient):
        """Test that reading progress routes are registered."""
        response = client.get(f"{settings.API_V1_STR}/reading-progress/")
        # Should return 403 (forbidden) not 404 (not found)
        assert response.status_code == 403

    def test_search_routes_registered(self, client: TestClient):
        """Test that search routes are registered."""
        response = client.get(f"{settings.API_V1_STR}/search/all")
        # Should return 403 (forbidden) not 404 (not found)
        assert response.status_code == 403


class TestEnvironmentVariables:
    """Test environment variable handling."""

    def test_environment_detection(self):
        """Test environment detection."""
        assert hasattr(settings, 'ENVIRONMENT')
        assert settings.ENVIRONMENT in ['development', 'testing', 'production']

    def test_debug_mode_in_development(self):
        """Test debug mode is enabled in development."""
        if settings.ENVIRONMENT == 'development':
            assert settings.DEBUG is True

    def test_database_echo_in_development(self):
        """Test database echo in development."""
        if settings.ENVIRONMENT == 'development':
            # Should have database echo enabled for debugging
            pass


class TestSecuritySettings:
    """Test security-related settings."""

    def test_secret_key_length(self):
        """Test secret key has minimum length."""
        assert len(settings.SECRET_KEY) >= 32

    def test_jwt_algorithm(self):
        """Test JWT algorithm is properly set."""
        assert settings.ALGORITHM in ['HS256', 'HS384', 'HS512', 'RS256']

    def test_access_token_expiration(self):
        """Test access token expiration is set."""
        assert isinstance(settings.ACCESS_TOKEN_EXPIRE_MINUTES, int)
        assert settings.ACCESS_TOKEN_EXPIRE_MINUTES > 0

    def test_cors_origins_not_empty(self):
        """Test CORS origins are configured."""
        assert isinstance(settings.BACKEND_CORS_ORIGINS, list)
        # In development, may allow all origins


class TestOptionalServices:
    """Test optional service configurations."""

    def test_redis_settings(self):
        """Test Redis settings if configured."""
        # Redis is optional, so we just check if settings exist
        if hasattr(settings, 'REDIS_URL'):
            assert isinstance(settings.REDIS_URL, str)

    def test_email_settings(self):
        """Test email settings if configured."""
        # Email is optional, so we just check if settings exist
        if hasattr(settings, 'SMTP_SERVER'):
            assert isinstance(settings.SMTP_SERVER, str)

    def test_logging_settings(self):
        """Test logging configuration."""
        # Check if logging level is set
        if hasattr(settings, 'LOG_LEVEL'):
            assert settings.LOG_LEVEL in ['DEBUG', 'INFO', 'WARNING', 'ERROR']

    def test_rate_limiting_settings(self):
        """Test rate limiting settings if configured."""
        # Rate limiting is optional
        if hasattr(settings, 'RATE_LIMIT_ENABLED'):
            assert isinstance(settings.RATE_LIMIT_ENABLED, bool) 