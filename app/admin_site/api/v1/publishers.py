from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status, Body
from sqlalchemy.orm import Session

from app.common.db.session import get_db
from app.admin_site.api.deps import get_current_admin, check_admin_permissions
from app.user_site.models.user import User
from app.admin_site.services import publisher_service
from app.user_site.schemas.publisher import (
    PublisherCreate,
    PublisherUpdate,
    PublisherResponse,
    PublisherListResponse,
    PublisherStatsResponse,
    BookResponse,
)
from app.core.exceptions import NotFoundException, ConflictException

router = APIRouter()


@router.get("/", response_model=PublisherListResponse)
async def get_all_publishers(
    skip: int = Query(0, description="Number of records to skip"),
    limit: int = Query(100, description="Max number of records to return"),
    search_query: Optional[str] = Query(None, description="Search by publisher name"),
    sort_by: str = Query("name", description="Field to sort by"),
    sort_desc: bool = Query(False, description="Sort in descending order"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["publisher:read", "publisher:list"])
    ),
):
    """
    Get all publishers with filtering options.
    """
    try:
        publishers = await publisher_service.get_all_publishers(
            db=db,
            skip=skip,
            limit=limit,
            search_query=search_query,
            sort_by=sort_by,
            sort_desc=sort_desc,
            admin_id=current_admin.id,
        )

        total_count = await publisher_service.count_publishers(
            db=db,
            name=search_query,
        )

        return PublisherListResponse(
            items=publishers,
            total=total_count,
            page=skip // limit + 1 if limit > 0 else 1,
            size=limit,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving publishers: {str(e)}",
        )


@router.get("/stats", response_model=PublisherStatsResponse)
async def get_publisher_statistics(
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["publisher:read", "stats:read"])
    ),
):
    """
    Get publisher statistics.
    """
    try:
        stats = await publisher_service.get_publisher_statistics(
            db=db,
            admin_id=current_admin.id,
        )
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving publisher statistics: {str(e)}",
        )


@router.get("/search", response_model=List[PublisherResponse])
async def search_publishers(
    query: str = Query(..., description="Search query"),
    skip: int = Query(0, description="Number of records to skip"),
    limit: int = Query(20, description="Max number of records to return"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["publisher:read"])),
):
    """
    Search publishers by name.
    """
    try:
        publishers = await publisher_service.search_publishers(
            db=db,
            query=query,
            skip=skip,
            limit=limit,
        )
        return publishers
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching publishers: {str(e)}",
        )


@router.get("/{publisher_id}", response_model=PublisherResponse)
async def get_publisher(
    publisher_id: int = Path(..., description="Publisher ID"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["publisher:read"])),
):
    """
    Get a publisher by ID.
    """
    try:
        publisher = await publisher_service.get_publisher_by_id(
            db=db,
            publisher_id=publisher_id,
            admin_id=current_admin.id,
        )
        return publisher
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving publisher: {str(e)}",
        )


@router.get("/slug/{slug}", response_model=PublisherResponse)
async def get_publisher_by_slug(
    slug: str = Path(..., description="Publisher slug"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["publisher:read"])),
):
    """
    Get a publisher by slug.
    """
    try:
        publisher = await publisher_service.get_publisher_by_slug(
            db=db,
            slug=slug,
        )
        return publisher
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving publisher: {str(e)}",
        )


@router.post("/", response_model=PublisherResponse, status_code=status.HTTP_201_CREATED)
async def create_publisher(
    publisher_data: PublisherCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["publisher:create"])),
):
    """
    Create a new publisher.
    """
    try:
        publisher = await publisher_service.create_publisher(
            db=db,
            publisher_data=publisher_data.model_dump(),
            admin_id=current_admin.id,
        )
        return publisher
    except ConflictException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating publisher: {str(e)}",
        )


@router.put("/{publisher_id}", response_model=PublisherResponse)
async def update_publisher(
    publisher_id: int = Path(..., description="Publisher ID"),
    publisher_data: PublisherUpdate = Body(...),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["publisher:update"])),
):
    """
    Update a publisher.
    """
    try:
        publisher = await publisher_service.update_publisher(
            db=db,
            publisher_id=publisher_id,
            publisher_data=publisher_data.model_dump(exclude_unset=True),
            admin_id=current_admin.id,
        )
        return publisher
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating publisher: {str(e)}",
        )


@router.delete("/{publisher_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_publisher(
    publisher_id: int = Path(..., description="Publisher ID"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["publisher:delete"])),
):
    """
    Delete a publisher.
    """
    try:
        await publisher_service.delete_publisher(
            db=db,
            publisher_id=publisher_id,
            admin_id=current_admin.id,
        )
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting publisher: {str(e)}",
        )


@router.get("/{publisher_id}/books", response_model=List[BookResponse])
async def get_publisher_books(
    publisher_id: int = Path(..., description="Publisher ID"),
    skip: int = Query(0, description="Number of records to skip"),
    limit: int = Query(20, description="Max number of records to return"),
    sort_by: str = Query("title", description="Field to sort by"),
    sort_desc: bool = Query(False, description="Sort in descending order"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["publisher:read", "book:read"])
    ),
):
    """
    Get books from a specific publisher.
    """
    try:
        books = await publisher_service.get_publisher_books(
            db=db,
            publisher_id=publisher_id,
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            sort_desc=sort_desc,
        )
        return books
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving publisher books: {str(e)}",
        )
