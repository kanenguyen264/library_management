from typing import Dict

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.auth import get_current_admin_user
from app.core.supabase_client import supabase_client
from app.models.user import User
from app.schemas.response import SuccessResponse

router = APIRouter()

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
}

ALLOWED_DOCUMENT_TYPES = {
    "application/pdf",
    "application/epub+zip",
    "application/x-mobipocket-ebook",
}

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_DOCUMENT_SIZE = 50 * 1024 * 1024  # 50MB


@router.post("/cover", response_model=SuccessResponse[Dict[str, str]])
async def upload_cover_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Upload book cover image to Supabase Storage (Admin only).
    """
    # Validate file type
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(ALLOWED_IMAGE_TYPES)}",
        )

    # Read file content
    try:
        file_content = await file.read()

        # Validate file size
        if len(file_content) > MAX_IMAGE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File size too large. Maximum allowed: {MAX_IMAGE_SIZE / (1024 * 1024):.1f}MB",
            )

        # Upload to Supabase
        public_url = supabase_client.upload_file(
            file_content=file_content,
            file_name=file.filename or "cover.jpg",
            content_type=file.content_type or "image/jpeg",
        )

        if not public_url:
            raise HTTPException(
                status_code=500, detail="Failed to upload image to storage"
            )

        return SuccessResponse(
            message="Cover image uploaded successfully", data={"url": public_url}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@router.post("/pdf", response_model=SuccessResponse[Dict[str, str]])
async def upload_pdf_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Upload PDF file to Supabase Storage (Admin only).
    """
    # Validate file type
    if file.content_type not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(ALLOWED_DOCUMENT_TYPES)}",
        )

    # Read file content
    try:
        file_content = await file.read()

        # Validate file size
        if len(file_content) > MAX_DOCUMENT_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File size too large. Maximum allowed: {MAX_DOCUMENT_SIZE / (1024 * 1024):.1f}MB",
            )

        # Upload to Supabase with pdf/ prefix
        public_url = supabase_client.upload_file(
            file_content=file_content,
            file_name=file.filename or "document.pdf",
            content_type=file.content_type or "application/pdf",
            folder="pdfs",
        )

        if not public_url:
            raise HTTPException(
                status_code=500, detail="Failed to upload PDF to storage"
            )

        return SuccessResponse(
            message="PDF uploaded successfully", data={"url": public_url}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@router.post("/epub", response_model=SuccessResponse[Dict[str, str]])
async def upload_epub_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Upload EPUB file to Supabase Storage (Admin only).
    """
    # Validate file type
    if file.content_type not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(ALLOWED_DOCUMENT_TYPES)}",
        )

    # Read file content
    try:
        file_content = await file.read()

        # Validate file size
        if len(file_content) > MAX_DOCUMENT_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File size too large. Maximum allowed: {MAX_DOCUMENT_SIZE / (1024 * 1024):.1f}MB",
            )

        # Upload to Supabase with epub/ prefix
        public_url = supabase_client.upload_file(
            file_content=file_content,
            file_name=file.filename or "document.epub",
            content_type=file.content_type or "application/epub+zip",
            folder="epubs",
        )

        if not public_url:
            raise HTTPException(
                status_code=500, detail="Failed to upload EPUB to storage"
            )

        return SuccessResponse(
            message="EPUB uploaded successfully", data={"url": public_url}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@router.post("/author-image", response_model=SuccessResponse[Dict[str, str]])
async def upload_author_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Upload author profile image to Supabase Storage (Admin only).
    """
    # Validate file type
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(ALLOWED_IMAGE_TYPES)}",
        )

    # Read file content
    try:
        file_content = await file.read()

        # Validate file size
        if len(file_content) > MAX_IMAGE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File size too large. Maximum allowed: {MAX_IMAGE_SIZE / (1024 * 1024):.1f}MB",
            )

        # Upload to Supabase with author-images/ prefix
        public_url = supabase_client.upload_file(
            file_content=file_content,
            file_name=file.filename or "author.jpg",
            content_type=file.content_type or "image/jpeg",
            folder="author-images",
        )

        if not public_url:
            raise HTTPException(
                status_code=500, detail="Failed to upload author image to storage"
            )

        return SuccessResponse(
            message="Author image uploaded successfully", data={"url": public_url}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@router.post("/user-avatar", response_model=SuccessResponse[Dict[str, str]])
async def upload_user_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Upload user avatar image to Supabase Storage (Admin only).
    """
    # Validate file type
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(ALLOWED_IMAGE_TYPES)}",
        )

    # Read file content
    try:
        file_content = await file.read()

        # Validate file size
        if len(file_content) > MAX_IMAGE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File size too large. Maximum allowed: {MAX_IMAGE_SIZE / (1024 * 1024):.1f}MB",
            )

        # Upload to Supabase Storage
        public_url = supabase_client.upload_file(
            file_content=file_content,
            file_name=file.filename or "avatar.jpg",
            content_type=file.content_type or "image/jpeg",
            folder="user-avatars",
        )

        if not public_url:
            raise HTTPException(
                status_code=500, detail="Failed to upload user avatar to storage"
            )

        return SuccessResponse(
            message="User avatar uploaded successfully", data={"url": public_url}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@router.post("/chapter-image", response_model=SuccessResponse[Dict[str, str]])
async def upload_chapter_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Upload chapter image to Supabase Storage (Admin only).
    """
    # Validate file type
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(ALLOWED_IMAGE_TYPES)}",
        )

    # Read file content
    try:
        file_content = await file.read()

        # Validate file size
        if len(file_content) > MAX_IMAGE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File size too large. Maximum allowed: {MAX_IMAGE_SIZE / (1024 * 1024):.1f}MB",
            )

        # Upload to Supabase with chapter-images/ prefix
        public_url = supabase_client.upload_file(
            file_content=file_content,
            file_name=file.filename or "chapter.jpg",
            content_type=file.content_type or "image/jpeg",
            folder="chapter-images",
        )

        if not public_url:
            raise HTTPException(
                status_code=500, detail="Failed to upload chapter image to storage"
            )

        return SuccessResponse(
            message="Chapter image uploaded successfully", data={"url": public_url}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@router.delete("/cover")
async def delete_cover_image(
    file_url: str,
    current_user: User = Depends(get_current_admin_user),
):
    """
    Delete cover image from Supabase Storage (Admin only).
    """
    try:
        success = supabase_client.delete_file(file_url)

        if success:
            return SuccessResponse(
                message="Image deleted successfully", data={"deleted": True}
            )
        else:
            raise HTTPException(status_code=400, detail="Failed to delete image")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting file: {str(e)}")


@router.delete("/document")
async def delete_document_file(
    file_url: str,
    current_user: User = Depends(get_current_admin_user),
):
    """
    Delete document file (PDF/EPUB) from Supabase Storage (Admin only).
    """
    try:
        success = supabase_client.delete_file(file_url)

        if success:
            return {"message": "Document deleted successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to delete document")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting file: {str(e)}")
