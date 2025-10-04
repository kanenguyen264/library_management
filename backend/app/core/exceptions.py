from fastapi import HTTPException, status


class BookNotFound(HTTPException):
    def __init__(self, book_id: int):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with id {book_id} not found",
        )


class AuthorNotFound(HTTPException):
    def __init__(self, author_id: int):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Author with id {author_id} not found",
        )


class CategoryNotFound(HTTPException):
    def __init__(self, category_id: int):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category with id {category_id} not found",
        )


class ChapterNotFound(HTTPException):
    def __init__(self, chapter_id: int):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter with id {chapter_id} not found",
        )


class DuplicateChapter(HTTPException):
    def __init__(self, book_id: int, chapter_number: int):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chapter {chapter_number} already exists for book {book_id}",
        )


class UserNotFound(HTTPException):
    def __init__(self, user_id: int):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found",
        )


class InvalidCredentials(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )


class DuplicateEmail(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )


class InsufficientPermissions(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
