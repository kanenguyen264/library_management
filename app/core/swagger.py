"""
Customized Swagger UI with categorized API documentation.

This module provides functionality to:
1. Create separate Swagger UI pages for different API categories
2. Filter OpenAPI schema by tags to show only relevant endpoints per category
3. Create a landing page that links to all category-specific documentation pages
"""

from fastapi import FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from starlette.responses import HTMLResponse, JSONResponse
from typing import Dict, List, Any, Optional, Callable
import copy
import functools

from app.core.config import get_settings
from app.logging.setup import get_logger

settings = get_settings()
logger = get_logger(__name__)

# Define categories for grouping tags
API_CATEGORIES = {
    # User API categories
    "books": ["Books", "Chapters", "Book Series", "Book Lists", "Publishers"],
    "users": [
        "Authentication",
        "Users",
        "Preferences",
        "Social Profiles",
        "Following",
    ],
    "social": ["Reviews", "Comments", "Discussions", "Notifications"],
    "content": ["Categories", "Authors", "Tags", "Quotes", "Annotations"],
    "reading": [
        "Reading Sessions",
        "Reading Goals",
        "Reading History",
        "reading-history",
        "Bookmarks",
        "Bookshelves",
    ],
    "gamification": [
        "Badges",
        "badges",
        "Achievements",
        "achievements",
    ],
    "recommendations": ["Recommendations", "Search", "recommendations", "search"],
    "payments": [
        "Payments",
        "Subscriptions",
        "Transactions",
        "payments",
        "subscriptions",
    ],
    # Admin API categories
    "admin-auth": ["Admin Auth", "Admin Sessions", "Admins"],
    "admin-users": ["Users Management"],
    "admin-books": [
        "Books Management",
        "Chapters Management",
        "Book Series Management",
        "Publishers Management",
    ],
    "admin-content": [
        "Authors Management",
        "Categories Management",
        "Tags Management",
        "Content Approval",
        "Featured Content",
    ],
    "admin-social": ["Reviews Management", "Discussions Management"],
    "admin-system": [
        "System Settings",
        "System Metrics",
        "System Health",
        "Logs Management",
        "Reports",
        "Analytics",
        "Dashboard",
        "Health",
    ],
    "admin-access": ["Roles", "Permissions"],
    "admin-marketing": [
        "Promotions",
        "Achievements",
        "Badges",
        "Subscriptions Management",
    ],
    # Legacy categories kept for backward compatibility
    "management": [
        "Books Management",
        "Users Management",
        "Authors Management",
        "Categories Management",
        "Chapters Management",
        "Tags Management",
        "Publishers Management",
        "Reviews Management",
        "Discussions Management",
        "Subscriptions Management",
        "Book Series Management",
    ],
    "admin": [
        "Analytics",
        "Reports",
        "Logs Management",
        "Dashboard",
        "System Settings",
        "System Metrics",
        "System Health",
        "Content Approval",
        "Featured Content",
        "Promotions",
        "Achievements",
        "Badges",
        "Admin Auth",
        "Admins",
        "Roles",
        "Permissions",
        "Admin Sessions",
    ],
}


def get_swagger_ui_html_with_categories(
    openapi_url: str, title: str, swagger_ui_parameters: Optional[Dict[str, Any]] = None
) -> HTMLResponse:
    """Generate custom Swagger UI HTML page with category information"""
    swagger_ui_parameters = swagger_ui_parameters or {}
    return get_swagger_ui_html(
        openapi_url=openapi_url,
        title=f"{title}",
        swagger_favicon_url="/static/favicon.ico",
        swagger_ui_parameters=swagger_ui_parameters,
    )


def filter_openapi_by_tags(
    app: FastAPI, category_name: str, tag_list: List[str]
) -> Dict[str, Any]:
    """Filter OpenAPI schema to include only specific tags"""
    # Get the original schema
    openapi_schema = get_openapi(
        title=f"{settings.PROJECT_NAME} - {category_name.title()} API",
        version=settings.PROJECT_VERSION,
        description=f"{settings.PROJECT_DESCRIPTION} - {category_name.title()} endpoints",
        routes=app.routes,
    )

    # Deep copy to avoid modifying the original
    filtered_schema = copy.deepcopy(openapi_schema)
    paths = filtered_schema.get("paths", {})

    # Filter paths to only include those with matching tags
    filtered_paths = {}
    for path, path_item in paths.items():
        # For each path, check each operation (GET, POST, etc.)
        for method, operation in path_item.items():
            if method.lower() in ["get", "post", "put", "delete", "patch"]:
                operation_tags = operation.get("tags", [])
                # Check if any of the operation's tags match our filter
                if any(tag in tag_list for tag in operation_tags):
                    # If path is not yet added to filtered_paths, add it
                    if path not in filtered_paths:
                        filtered_paths[path] = {}
                    # Add this method to the path
                    filtered_paths[path][method] = operation

    # Replace the paths in the schema with our filtered paths
    filtered_schema["paths"] = filtered_paths

    # Filter the tags list to only include relevant tags
    if "tags" in filtered_schema:
        filtered_schema["tags"] = [
            tag for tag in filtered_schema["tags"] if tag.get("name") in tag_list
        ]

    return filtered_schema


# Factory functions to create route handlers with proper closures
def create_openapi_route_handler(
    app: FastAPI, category: str, tags: List[str]
) -> Callable:
    """Create a handler for category OpenAPI schema endpoint"""

    async def get_category_openapi():
        return JSONResponse(filter_openapi_by_tags(app, category, tags))

    return get_category_openapi


def create_docs_route_handler(category: str) -> Callable:
    """Create a handler for category Swagger UI endpoint"""

    async def get_category_docs():
        return get_swagger_ui_html_with_categories(
            openapi_url=f"/openapi-{category}.json",
            title=f"{settings.PROJECT_NAME} - {category.title()} API",
        )

    return get_category_docs


def setup_categorized_swagger_ui(app: FastAPI):
    """Set up categorized Swagger UI endpoints"""
    # Disable the default docs
    app.docs_url = None
    app.redoc_url = None

    # Main documentation page
    @app.get("/docs", include_in_schema=False)
    async def get_documentation():
        """Main documentation page with links to category docs"""
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>API Documentation - ReadingBook API</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css">
            <style>
                body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding-bottom: 40px; }
                .card { margin-bottom: 20px; transition: transform 0.2s; box-shadow: 0 4px 8px rgba(0,0,0,0.1); border: none; }
                .card:hover { transform: translateY(-5px); box-shadow: 0 10px 20px rgba(0,0,0,0.15); }
                .header { background-color: #343a40; color: white; padding: 30px 0; margin-bottom: 30px; }
                .category-container { max-width: 1000px; margin: 0 auto; }
                .card-title { font-size: 1.3rem; font-weight: 600; }
                .btn-primary { background-color: #3273dc; border-color: #3273dc; }
                .btn-primary:hover { background-color: #2366d1; border-color: #2366d1; }
                .btn-outline-secondary:hover { background-color: #f5f5f5; color: #333; border-color: #ddd; }
                footer { margin-top: 40px; color: #6c757d; }
                .card-body { padding: 1.5rem; }
            </style>
        </head>
        <body>
            <div class="header">
                <div class="container">
                    <h1>ReadingBook API Documentation</h1>
                    <p>Select a category to explore the API endpoints</p>
                </div>
            </div>
            
            <div class="container category-container">
                <div class="row">
        """

        # Add cards for each category
        for category, tags in API_CATEGORIES.items():
            html_content += f"""
                    <div class="col-md-4">
                        <div class="card">
                            <div class="card-body">
                                <h5 class="card-title">{category.title()} API</h5>
                                <p class="card-text">Documentation for {category.title()} related endpoints</p>
                                <a href="/docs/{category}" class="btn btn-primary w-100">View Docs</a>
                            </div>
                        </div>
                    </div>
            """

        # Complete the HTML
        html_content += """
                </div>
                <div class="mt-4 text-center">
                    <a href="/docs/all" class="btn btn-outline-secondary">View All Endpoints</a>
                </div>
            </div>
            
            <footer class="text-center mt-5 mb-3">
                <p>&copy; ReadingBook API</p>
            </footer>
        </body>
        </html>
        """

        return HTMLResponse(content=html_content)

    # Full OpenAPI schema
    @app.get("/openapi.json", include_in_schema=False)
    async def get_open_api_endpoint():
        return JSONResponse(
            get_openapi(
                title=settings.PROJECT_NAME,
                version=settings.PROJECT_VERSION,
                description=settings.PROJECT_DESCRIPTION,
                routes=app.routes,
            )
        )

    # Complete Swagger UI (all endpoints)
    @app.get("/docs/all", include_in_schema=False)
    async def get_all_documentation():
        return get_swagger_ui_html_with_categories(
            openapi_url="/openapi.json", title=f"{settings.PROJECT_NAME} - Complete API"
        )

    # Category-specific OpenAPI schemas and Swagger UIs
    for category, tags in API_CATEGORIES.items():
        # Use factory functions to create route handlers with proper closures
        openapi_handler = create_openapi_route_handler(app, category, tags)
        docs_handler = create_docs_route_handler(category)

        # Add the routes to the app
        app.add_api_route(
            f"/openapi-{category}.json",
            openapi_handler,
            methods=["GET"],
            include_in_schema=False,
        )
        app.add_api_route(
            f"/docs/{category}", docs_handler, methods=["GET"], include_in_schema=False
        )
