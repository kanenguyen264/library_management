from typing import List, Optional, Dict, Any
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Query,
    status,
    Body,
    UploadFile,
    File,
)
from sqlalchemy.orm import Session
from datetime import datetime

from app.common.db.session import get_db
from app.admin_site.api.deps import get_current_admin, check_admin_permissions
from app.user_site.models.user import User
from app.user_site.models.chapter import Chapter, ChapterMedia
from app.admin_site.services import chapter_service
from app.user_site.schemas.chapter import (
    ChapterCreate,
    ChapterUpdate,
    ChapterResponse,
    ChapterListResponse,
    ChapterMediaCreate,
    ChapterMediaResponse,
    ChapterStatsResponse,
    ChapterStatus,
)
from app.core.exceptions import NotFoundException, ForbiddenException

router = APIRouter()


@router.get("/", response_model=ChapterListResponse)
async def get_all_chapters(
    skip: int = Query(0, description="Number of records to skip"),
    limit: int = Query(100, description="Max number of records to return"),
    book_id: Optional[int] = Query(None, description="Filter by book ID"),
    is_published: Optional[bool] = Query(
        None, description="Filter by published status"
    ),
    search_query: Optional[str] = Query(None, description="Search by title or content"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["chapter:read", "chapter:list"])
    ),
):
    """
    Get list of chapters with filtering options.
    """
    try:
        chapters = await chapter_service.get_all_chapters(
            db=db,
            skip=skip,
            limit=limit,
            book_id=book_id,
            is_published=is_published,
            search_query=search_query,
        )

        total_count = await chapter_service.count_chapters(
            db=db,
            book_id=book_id,
            is_published=is_published,
            search_query=search_query,
        )

        return ChapterListResponse(
            items=chapters,
            total=total_count,
            page=skip // limit + 1 if limit > 0 else 1,
            size=limit,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving chapters: {str(e)}",
        )


@router.get("/{chapter_id}", response_model=ChapterResponse)
async def get_chapter(
    chapter_id: int = Path(..., description="Chapter ID"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["chapter:read"])),
):
    """
    Get a chapter by ID.
    """
    try:
        chapter = await chapter_service.get_chapter_by_id(
            db=db,
            chapter_id=chapter_id,
        )
        return chapter
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving chapter: {str(e)}",
        )


@router.get("/book/{book_id}", response_model=ChapterListResponse)
async def get_book_chapters(
    book_id: int = Path(..., description="Book ID"),
    skip: int = Query(0, description="Number of records to skip"),
    limit: int = Query(20, description="Max number of records to return"),
    is_published: Optional[bool] = Query(
        None, description="Filter by published status"
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["chapter:read"])),
):
    """
    Get chapters for a specific book.
    """
    try:
        chapters = await chapter_service.get_book_chapters(
            db=db,
            book_id=book_id,
            skip=skip,
            limit=limit,
            is_published=is_published,
        )

        total_count = await chapter_service.count_chapters(
            db=db,
            book_id=book_id,
            is_published=is_published,
        )

        return ChapterListResponse(
            items=chapters,
            total=total_count,
            page=skip // limit + 1 if limit > 0 else 1,
            size=limit,
        )
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving book chapters: {str(e)}",
        )


@router.post("/", response_model=ChapterResponse, status_code=status.HTTP_201_CREATED)
async def create_chapter(
    chapter_data: ChapterCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["chapter:create"])),
):
    """
    Create a new chapter.
    """
    try:
        chapter = await chapter_service.create_chapter(
            db=db,
            chapter_data=chapter_data.model_dump(),
        )
        return chapter
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ForbiddenException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating chapter: {str(e)}",
        )


@router.put("/{chapter_id}", response_model=ChapterResponse)
async def update_chapter(
    chapter_id: int = Path(..., description="Chapter ID"),
    chapter_data: ChapterUpdate = Body(...),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["chapter:update"])),
):
    """
    Update a chapter.
    """
    try:
        chapter = await chapter_service.update_chapter(
            db=db,
            chapter_id=chapter_id,
            chapter_data=chapter_data.model_dump(exclude_unset=True),
        )
        return chapter
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ForbiddenException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating chapter: {str(e)}",
        )


@router.delete("/{chapter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chapter(
    chapter_id: int = Path(..., description="Chapter ID"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["chapter:delete"])),
):
    """
    Delete a chapter.
    """
    try:
        await chapter_service.delete_chapter(
            db=db,
            chapter_id=chapter_id,
        )
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting chapter: {str(e)}",
        )


@router.post("/{chapter_id}/publish", response_model=ChapterResponse)
async def publish_chapter(
    chapter_id: int = Path(..., description="Chapter ID"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["chapter:update", "chapter:publish"])
    ),
):
    """
    Publish a chapter.
    """
    try:
        chapter = await chapter_service.publish_chapter(
            db=db,
            chapter_id=chapter_id,
        )
        return chapter
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error publishing chapter: {str(e)}",
        )


@router.post("/{chapter_id}/unpublish", response_model=ChapterResponse)
async def unpublish_chapter(
    chapter_id: int = Path(..., description="Chapter ID"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["chapter:update", "chapter:publish"])
    ),
):
    """
    Unpublish a chapter.
    """
    try:
        chapter = await chapter_service.unpublish_chapter(
            db=db,
            chapter_id=chapter_id,
        )
        return chapter
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error unpublishing chapter: {str(e)}",
        )


@router.post("/{chapter_id}/reorder", response_model=ChapterResponse)
async def reorder_chapter(
    chapter_id: int = Path(..., description="Chapter ID"),
    new_number: int = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["chapter:update"])),
):
    """
    Change chapter order in a book.
    """
    try:
        chapter = await chapter_service.reorder_chapter(
            db=db,
            chapter_id=chapter_id,
            new_number=new_number,
        )
        return chapter
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ForbiddenException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error reordering chapter: {str(e)}",
        )


@router.get("/{chapter_id}/media", response_model=List[ChapterMediaResponse])
async def get_chapter_media(
    chapter_id: int = Path(..., description="Chapter ID"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["chapter:read"])),
):
    """
    Get media associated with a chapter.
    """
    try:
        media_items = await chapter_service.get_chapter_media(
            db=db,
            chapter_id=chapter_id,
        )
        return media_items
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving chapter media: {str(e)}",
        )


@router.post("/{chapter_id}/media", response_model=ChapterMediaResponse)
async def add_media_to_chapter(
    chapter_id: int = Path(..., description="Chapter ID"),
    media_data: ChapterMediaCreate = Body(...),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["chapter:update", "media:create"])
    ),
):
    """
    Add media to a chapter.
    """
    try:
        # Add chapter_id to media_data
        media_data_dict = media_data.model_dump()
        media_data_dict["chapter_id"] = chapter_id

        media = await chapter_service.add_media_to_chapter(
            db=db,
            media_data=media_data_dict,
        )
        return media
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error adding media to chapter: {str(e)}",
        )


@router.delete("/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chapter_media(
    media_id: int = Path(..., description="Media ID"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["chapter:update", "media:delete"])
    ),
):
    """
    Delete chapter media.
    """
    try:
        await chapter_service.delete_chapter_media(
            db=db,
            media_id=media_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting chapter media: {str(e)}",
        )


@router.get("/stats", response_model=ChapterStatsResponse)
async def get_chapter_statistics(
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["chapter:read", "stats:read"])
    ),
):
    """
    Get chapter statistics.
    """
    try:
        stats = await chapter_service.get_chapter_statistics(db=db)
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving chapter statistics: {str(e)}",
        )


@router.post("/scheduled/process", response_model=List[ChapterResponse])
async def process_scheduled_chapters(
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["chapter:update", "chapter:publish"])
    ),
):
    """
    Process chapters scheduled for publication.
    """
    try:
        published_chapters = await chapter_service.check_and_publish_scheduled_chapters(
            db=db
        )
        return published_chapters
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing scheduled chapters: {str(e)}",
        )
