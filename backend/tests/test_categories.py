"""
Test category management endpoints.
"""
import pytest
from app.crud.category import crud_category
from app.models.category import Category
from app.schemas.category import CategoryCreate
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.orm import Session


class TestCategoryEndpoints:
    """Test category management API endpoints."""

    def test_read_categories_success(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_category: Category):
        """Test reading categories list."""
        response = client.get(f"{api_v1_prefix}/categories/", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) > 0
        
        # Check category data structure
        category_data = data["data"][0]
        assert "id" in category_data
        assert "name" in category_data
        assert "description" in category_data
        assert "slug" in category_data
        assert "is_active" in category_data
        assert "created_at" in category_data

    def test_read_categories_unauthorized(self, client: TestClient, api_v1_prefix: str):
        """Test reading categories without authentication."""
        response = client.get(f"{api_v1_prefix}/categories/")
        
        assert response.status_code == 403

    def test_read_categories_pagination(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, db_session: Session):
        """Test reading categories with pagination."""
        # Create multiple categories
        for i in range(5):
            category_data = {
                "name": f"Category {i}",
                "description": f"Description of Category {i}",
                "slug": f"category-{i}",
                "is_active": True,
            }
            category_in = CategoryCreate(**category_data)
            crud_category.create(db_session, obj_in=category_in)
        
        # Test pagination
        response = client.get(f"{api_v1_prefix}/categories/?skip=0&limit=3", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) <= 3

    def test_create_category_admin(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test creating category as admin."""
        category_data = {
            "name": "Science Fiction",
            "description": "Science fiction books and novels",
            "slug": "science-fiction",
            "is_active": True,
        }
        
        response = client.post(f"{api_v1_prefix}/categories/", json=category_data, headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["name"] == category_data["name"]
        assert data["data"]["description"] == category_data["description"]
        assert data["data"]["slug"] == category_data["slug"]
        assert data["data"]["is_active"] == category_data["is_active"]
        assert "id" in data["data"]
        assert "created_at" in data["data"]

    def test_create_category_non_admin(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test creating category as non-admin user."""
        category_data = {
            "name": "Romance",
            "description": "Romance books and novels",
            "slug": "romance",
            "is_active": True,
        }
        
        response = client.post(f"{api_v1_prefix}/categories/", json=category_data, headers=auth_headers)
        
        assert response.status_code == 403

    def test_create_category_missing_required_fields(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test creating category without required fields."""
        category_data = {
            "description": "Category without name and slug",
        }
        
        response = client.post(f"{api_v1_prefix}/categories/", json=category_data, headers=admin_headers)
        
        assert response.status_code == 422

    def test_create_category_duplicate_name(self, client: TestClient, api_v1_prefix: str, admin_headers: dict, test_category: Category):
        """Test creating category with duplicate name."""
        category_data = {
            "name": test_category.name,
            "description": "Duplicate category name",
            "slug": "duplicate-category",
            "is_active": True,
        }
        
        response = client.post(f"{api_v1_prefix}/categories/", json=category_data, headers=admin_headers)
        
        # Should succeed since name uniqueness is handled at database level
        # Or should return 400 if there's a constraint
        assert response.status_code in [200, 400]

    def test_read_category_by_id_success(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_category: Category):
        """Test reading category by ID."""
        response = client.get(f"{api_v1_prefix}/categories/{test_category.id}", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["id"] == test_category.id
        assert data["data"]["name"] == test_category.name
        assert data["data"]["description"] == test_category.description
        assert data["data"]["slug"] == test_category.slug
        assert data["data"]["is_active"] == test_category.is_active

    def test_read_category_by_id_not_found(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test reading non-existent category by ID."""
        response = client.get(f"{api_v1_prefix}/categories/99999", headers=auth_headers)
        
        assert response.status_code == 404

    def test_read_category_by_id_unauthorized(self, client: TestClient, api_v1_prefix: str, test_category: Category):
        """Test reading category by ID without authentication."""
        response = client.get(f"{api_v1_prefix}/categories/{test_category.id}")
        
        assert response.status_code == 403

    def test_update_category_admin(self, client: TestClient, api_v1_prefix: str, admin_headers: dict, test_category: Category):
        """Test updating category as admin."""
        update_data = {
            "name": "Updated Category Name",
            "description": "Updated description",
            "slug": "updated-category",
            "is_active": False,
        }
        
        response = client.put(f"{api_v1_prefix}/categories/{test_category.id}", json=update_data, headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["name"] == update_data["name"]
        assert data["data"]["description"] == update_data["description"]
        assert data["data"]["slug"] == update_data["slug"]
        assert data["data"]["is_active"] == update_data["is_active"]

    def test_update_category_non_admin(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_category: Category):
        """Test updating category as non-admin user."""
        update_data = {
            "name": "Unauthorized Update",
        }
        
        response = client.put(f"{api_v1_prefix}/categories/{test_category.id}", json=update_data, headers=auth_headers)
        
        assert response.status_code == 403

    def test_update_category_not_found(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test updating non-existent category."""
        update_data = {
            "name": "Updated Name",
        }
        
        response = client.put(f"{api_v1_prefix}/categories/99999", json=update_data, headers=admin_headers)
        
        assert response.status_code == 404

    def test_delete_category_admin(self, client: TestClient, api_v1_prefix: str, admin_headers: dict, db_session: Session):
        """Test deleting category as admin."""
        # Create category to delete
        category_data = {
            "name": "To Delete Category",
            "description": "Category to be deleted",
            "slug": "to-delete-category",
            "is_active": True,
        }
        category_in = CategoryCreate(**category_data)
        category = crud_category.create(db_session, obj_in=category_in)
        
        response = client.delete(f"{api_v1_prefix}/categories/{category.id}", headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data

    def test_delete_category_non_admin(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, test_category: Category):
        """Test deleting category as non-admin user."""
        response = client.delete(f"{api_v1_prefix}/categories/{test_category.id}", headers=auth_headers)
        
        assert response.status_code == 403

    def test_delete_category_not_found(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test deleting non-existent category."""
        response = client.delete(f"{api_v1_prefix}/categories/99999", headers=admin_headers)
        
        assert response.status_code == 404

    def test_read_active_categories_success(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, db_session: Session):
        """Test reading active categories."""
        # Create active and inactive categories
        for i in range(3):
            category_data = {
                "name": f"Active Category {i}",
                "description": f"Active category {i}",
                "slug": f"active-category-{i}",
                "is_active": True,
            }
            category_in = CategoryCreate(**category_data)
            crud_category.create(db_session, obj_in=category_in)
        
        for i in range(2):
            category_data = {
                "name": f"Inactive Category {i}",
                "description": f"Inactive category {i}",
                "slug": f"inactive-category-{i}",
                "is_active": False,
            }
            category_in = CategoryCreate(**category_data)
            crud_category.create(db_session, obj_in=category_in)
        
        response = client.get(f"{api_v1_prefix}/categories/active", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        
        # All returned categories should be active
        for category in data["data"]:
            assert category["is_active"] is True

    def test_read_active_categories_pagination(self, client: TestClient, api_v1_prefix: str, auth_headers: dict, db_session: Session):
        """Test reading active categories with pagination."""
        # Create multiple active categories
        for i in range(5):
            category_data = {
                "name": f"Active Paginated Category {i}",
                "description": f"Active paginated category {i}",
                "slug": f"active-paginated-category-{i}",
                "is_active": True,
            }
            category_in = CategoryCreate(**category_data)
            crud_category.create(db_session, obj_in=category_in)
        
        # Test pagination
        response = client.get(f"{api_v1_prefix}/categories/active?skip=0&limit=3", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) <= 3

    def test_read_active_categories_unauthorized(self, client: TestClient, api_v1_prefix: str):
        """Test reading active categories without authentication."""
        response = client.get(f"{api_v1_prefix}/categories/active")
        
        assert response.status_code == 403


class TestCategoryCRUD:
    """Test category CRUD operations."""

    def test_create_category_crud(self, db_session: Session):
        """Test creating category through CRUD."""
        category_data = {
            "name": "CRUD Category",
            "description": "Category created through CRUD",
            "slug": "crud-category",
            "is_active": True,
        }
        category_in = CategoryCreate(**category_data)
        category = crud_category.create(db_session, obj_in=category_in)
        
        assert category.name == category_data["name"]
        assert category.description == category_data["description"]
        assert category.slug == category_data["slug"]
        assert category.is_active == category_data["is_active"]
        assert category.id is not None

    def test_get_category_by_name(self, db_session: Session, test_category: Category):
        """Test getting category by name."""
        category = crud_category.get_by_name(db_session, name=test_category.name)
        
        assert category is not None
        assert category.name == test_category.name
        assert category.id == test_category.id

    def test_get_category_by_name_not_found(self, db_session: Session):
        """Test getting category by non-existent name."""
        category = crud_category.get_by_name(db_session, name="Nonexistent Category")
        
        assert category is None

    def test_get_category_by_slug(self, db_session: Session, test_category: Category):
        """Test getting category by slug."""
        category = crud_category.get_by_slug(db_session, slug=test_category.slug)
        
        assert category is not None
        assert category.slug == test_category.slug
        assert category.id == test_category.id

    def test_get_category_by_slug_not_found(self, db_session: Session):
        """Test getting category by non-existent slug."""
        category = crud_category.get_by_slug(db_session, slug="nonexistent-slug")
        
        assert category is None

    def test_get_active_categories(self, db_session: Session):
        """Test getting active categories."""
        # Create active and inactive categories
        for i in range(3):
            category_data = {
                "name": f"Active CRUD Category {i}",
                "description": f"Active CRUD category {i}",
                "slug": f"active-crud-category-{i}",
                "is_active": True,
            }
            category_in = CategoryCreate(**category_data)
            crud_category.create(db_session, obj_in=category_in)
        
        for i in range(2):
            category_data = {
                "name": f"Inactive CRUD Category {i}",
                "description": f"Inactive CRUD category {i}",
                "slug": f"inactive-crud-category-{i}",
                "is_active": False,
            }
            category_in = CategoryCreate(**category_data)
            crud_category.create(db_session, obj_in=category_in)
        
        active_categories = crud_category.get_active(db_session)
        
        assert isinstance(active_categories, list)
        assert len(active_categories) >= 3
        
        # All returned categories should be active
        for category in active_categories:
            assert category.is_active is True

    def test_search_categories_by_name(self, db_session: Session, test_category: Category):
        """Test searching categories by name."""
        search_term = test_category.name.split()[0]
        categories = crud_category.search_by_name(db_session, name=search_term)
        
        assert isinstance(categories, list)
        assert len(categories) > 0
        found_category = any(category.id == test_category.id for category in categories)
        assert found_category

    def test_search_categories_by_name_no_results(self, db_session: Session):
        """Test searching categories with no results."""
        categories = crud_category.search_by_name(db_session, name="NonexistentCategory")
        
        assert isinstance(categories, list)
        assert len(categories) == 0

    def test_update_category_crud(self, db_session: Session, test_category: Category):
        """Test updating category through CRUD."""
        update_data = {
            "description": "Updated description through CRUD",
            "is_active": False,
        }
        
        updated_category = crud_category.update(db_session, db_obj=test_category, obj_in=update_data)
        
        assert updated_category.description == update_data["description"]
        assert updated_category.is_active == update_data["is_active"]
        assert updated_category.name == test_category.name  # Unchanged
        assert updated_category.slug == test_category.slug  # Unchanged

    def test_delete_category_crud(self, db_session: Session):
        """Test deleting category through CRUD."""
        # Create category to delete
        category_data = {
            "name": "Category to Delete",
            "description": "This category will be deleted",
            "slug": "category-to-delete",
            "is_active": True,
        }
        category_in = CategoryCreate(**category_data)
        category = crud_category.create(db_session, obj_in=category_in)
        category_id = category.id
        
        # Delete category
        deleted_category = crud_category.remove(db_session, id=category_id)
        
        assert deleted_category.id == category_id
        assert deleted_category.name == category.name
        
        # Verify category is deleted
        retrieved_category = crud_category.get(db_session, id=category_id)
        assert retrieved_category is None

    def test_get_multi_categories_crud(self, db_session: Session):
        """Test getting multiple categories through CRUD."""
        # Create multiple categories
        for i in range(5):
            category_data = {
                "name": f"Multi Category {i}",
                "description": f"Description {i}",
                "slug": f"multi-category-{i}",
                "is_active": True,
            }
            category_in = CategoryCreate(**category_data)
            crud_category.create(db_session, obj_in=category_in)
        
        categories = crud_category.get_multi(db_session, skip=0, limit=3)
        
        assert isinstance(categories, list)
        assert len(categories) <= 3

    def test_count_categories_crud(self, db_session: Session):
        """Test counting categories through CRUD."""
        # Create multiple categories
        initial_count = crud_category.count(db_session)
        
        for i in range(3):
            category_data = {
                "name": f"Count Category {i}",
                "description": f"Description {i}",
                "slug": f"count-category-{i}",
                "is_active": True,
            }
            category_in = CategoryCreate(**category_data)
            crud_category.create(db_session, obj_in=category_in)
        
        final_count = crud_category.count(db_session)
        
        assert final_count == initial_count + 3


@pytest.mark.asyncio
class TestCategoryEndpointsAsync:
    """Test category endpoints with async client."""

    async def test_read_categories_async(self, async_client: AsyncClient, api_v1_prefix: str, auth_headers: dict):
        """Test reading categories list async."""
        response = await async_client.get(f"{api_v1_prefix}/categories/", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list)

    async def test_create_category_async(self, async_client: AsyncClient, api_v1_prefix: str, admin_headers: dict):
        """Test creating category async."""
        category_data = {
            "name": "Async Category",
            "description": "Category created asynchronously",
            "slug": "async-category",
            "is_active": True,
        }
        
        response = await async_client.post(f"{api_v1_prefix}/categories/", json=category_data, headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert data["data"]["name"] == category_data["name"]

    async def test_read_active_categories_async(self, async_client: AsyncClient, api_v1_prefix: str, auth_headers: dict):
        """Test reading active categories async."""
        response = await async_client.get(f"{api_v1_prefix}/categories/active", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert isinstance(data["data"], list) 