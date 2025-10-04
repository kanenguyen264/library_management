from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel

# Generic type for data payload
T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """Standard API response schema with message support"""

    success: bool = True
    message: str
    data: Optional[T] = None
    errors: Optional[List[str]] = None
    meta: Optional[Dict[str, Any]] = None


class SuccessResponse(APIResponse[T]):
    """Success response with data"""

    success: bool = True
    message: str = "Operation completed successfully"
    data: Optional[T] = None
    meta: Optional[Dict[str, Any]] = None


class ErrorResponse(APIResponse[None]):
    """Error response with error details"""

    success: bool = False
    message: str = "An error occurred"
    data: None = None
    errors: Optional[List[str]] = None


class CreateResponse(APIResponse[T]):
    """Response for create operations"""

    success: bool = True
    message: str = "Created successfully"
    data: Optional[T] = None


class UpdateResponse(APIResponse[T]):
    """Response for update operations"""

    success: bool = True
    message: str = "Updated successfully"
    data: Optional[T] = None


class DeleteResponse(APIResponse[None]):
    """Response for delete operations"""

    success: bool = True
    message: str = "Deleted successfully"
    data: None = None


class ListResponse(APIResponse[List[T]]):
    """Response for list operations"""

    success: bool = True
    message: str = "Data retrieved successfully"
    data: Optional[List[T]] = None
    meta: Optional[Dict[str, Any]] = None


# Specific success messages for different operations
class Messages:
    # User messages
    USER_CREATED = "User created successfully"
    USER_UPDATED = "User profile updated successfully"
    USER_DELETED = "User deleted successfully"
    USER_NOT_FOUND = "User not found"
    USER_ALREADY_EXISTS = "User with this email already exists"

    # Book messages
    BOOK_CREATED = "Book created successfully"
    BOOK_UPDATED = "Book updated successfully"
    BOOK_DELETED = "Book deleted successfully"
    BOOK_NOT_FOUND = "Book not found"
    BOOKS_RETRIEVED = "Books retrieved successfully"

    # Author messages
    AUTHOR_CREATED = "Author created successfully"
    AUTHOR_UPDATED = "Author updated successfully"
    AUTHOR_DELETED = "Author deleted successfully"
    AUTHOR_NOT_FOUND = "Author not found"
    AUTHORS_RETRIEVED = "Authors retrieved successfully"

    # Category messages
    CATEGORY_CREATED = "Category created successfully"
    CATEGORY_UPDATED = "Category updated successfully"
    CATEGORY_DELETED = "Category deleted successfully"
    CATEGORY_NOT_FOUND = "Category not found"
    CATEGORY_ALREADY_EXISTS = "Category with this name already exists"
    CATEGORIES_RETRIEVED = "Categories retrieved successfully"

    # Chapter messages
    CHAPTER_CREATED = "Chapter created successfully"
    CHAPTER_UPDATED = "Chapter updated successfully"
    CHAPTER_DELETED = "Chapter deleted successfully"
    CHAPTER_NOT_FOUND = "Chapter not found"
    CHAPTER_DUPLICATE = "Chapter with this number already exists for this book"
    CHAPTERS_RETRIEVED = "Chapters retrieved successfully"

    # Reading Progress messages
    READING_PROGRESS_CREATED = "Reading progress created successfully"
    READING_PROGRESS_UPDATED = "Reading progress updated successfully"
    READING_PROGRESS_DELETED = "Reading progress deleted successfully"
    READING_PROGRESS_NOT_FOUND = "Reading progress not found"
    READING_PROGRESS_RETRIEVED = "Reading progress retrieved successfully"

    # Favorite messages
    FAVORITE_ADDED = "Book added to favorites successfully"
    FAVORITE_REMOVED = "Book removed from favorites successfully"
    FAVORITE_NOT_FOUND = "Favorite not found"
    FAVORITE_ALREADY_EXISTS = "Book is already in favorites"
    FAVORITES_RETRIEVED = "Favorites retrieved successfully"

    # Reading List messages
    READING_LIST_CREATED = "Reading list created successfully"
    READING_LIST_UPDATED = "Reading list updated successfully"
    READING_LIST_DELETED = "Reading list deleted successfully"
    READING_LIST_NOT_FOUND = "Reading list not found"
    READING_LIST_ITEM_ADDED = "Book added to reading list successfully"
    READING_LIST_ITEM_UPDATED = "Reading list item updated successfully"
    READING_LIST_ITEM_REMOVED = "Book removed from reading list successfully"
    READING_LISTS_RETRIEVED = "Reading lists retrieved successfully"

    # Authentication messages
    LOGIN_SUCCESS = "Login successful"
    LOGIN_SUCCESSFUL = "Login successful"  # Compatibility with tests
    LOGOUT_SUCCESS = "Logout successful"
    REGISTER_SUCCESS = "Registration successful"
    TOKEN_REFRESH_SUCCESS = "Token refreshed successfully"
    PASSWORD_CHANGED = "Password changed successfully"
    PASSWORD_RESET_SENT = "Password reset email sent successfully"
    PASSWORD_RESET_SUCCESS = "Password reset successful"
    INCORRECT_CREDENTIALS = "Invalid credentials"
    INACTIVE_USER = "Inactive user"

    # File upload messages
    FILE_UPLOADED = "File uploaded successfully"
    FILE_DELETED = "File deleted successfully"
    FILE_NOT_FOUND = "File not found"
    INVALID_FILE_TYPE = "Invalid file type"
    FILE_TOO_LARGE = "File size exceeds maximum limit"

    # Search messages
    SEARCH_COMPLETED = "Search completed successfully"

    # General messages
    OPERATION_SUCCESS = "Operation completed successfully"
    DATA_RETRIEVED = "Data retrieved successfully"
    INVALID_REQUEST = "Invalid request data"
    UNAUTHORIZED = "Unauthorized access"
    FORBIDDEN = "Access forbidden"
    NOT_FOUND = "Resource not found"
    INTERNAL_ERROR = "Internal server error occurred"
