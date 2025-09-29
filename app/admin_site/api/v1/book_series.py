from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status, Body
from sqlalchemy.orm import Session

from app.common.db.session import get_db
from app.admin_site.api.deps import get_current_admin, check_admin_permissions
from app.user_site.models.user import User
from app.user_site.models.book_series import BookSeries, BookSeriesItem
from app.admin_site.services import book_series_service
from app.user_site.schemas.book_series import (
    BookSeriesCreate,
    BookSeriesUpdate,
    BookSeriesResponse,
    BookSeriesListResponse,
    BookSeriesItemCreate,
    BookSeriesItemResponse,
    BookSeriesItemListResponse,
    BookSeriesStatsResponse,
)
from app.core.exceptions import NotFoundException, ForbiddenException

router = APIRouter()

# Danh sách endpoints:
# GET /                   - Lấy danh sách tất cả các bộ sách (series)
# GET /{series_id}        - Lấy thông tin chi tiết của một bộ sách theo ID
# POST /                  - Tạo mới một bộ sách
# PUT /{series_id}        - Cập nhật thông tin của một bộ sách
# DELETE /{series_id}     - Xóa một bộ sách
# GET /{series_id}/books  - Lấy danh sách các sách trong một bộ
# POST /{series_id}/books - Thêm một sách vào bộ
# DELETE /books/{item_id} - Xóa một sách khỏi bộ
# PUT /books/{item_id}    - Cập nhật vị trí của sách trong bộ
# GET /stats              - Lấy thống kê về các bộ sách


@router.get("/", response_model=BookSeriesListResponse)
async def get_all_series(
    skip: int = Query(0, description="Number of records to skip"),
    limit: int = Query(100, description="Max number of records to return"),
    search_query: Optional[str] = Query(None, description="Search by series name"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["book_series:read", "book_series:list"])
    ),
):
    """
    Get all book series with filtering options.
    """
    try:
        series_list = await book_series_service.get_all_series(
            db=db,
            skip=skip,
            limit=limit,
            search_query=search_query,
            admin_id=current_admin.id,
        )

        total_count = await book_series_service.count_series(
            db=db,
            search_query=search_query,
        )

        return BookSeriesListResponse(
            items=series_list,
            total=total_count,
            page=skip // limit + 1 if limit > 0 else 1,
            size=limit,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving book series: {str(e)}",
        )


@router.get("/{series_id}", response_model=BookSeriesResponse)
async def get_series(
    series_id: int = Path(..., description="Series ID"),
    include_items: bool = Query(False, description="Include books in series"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["book_series:read"])),
):
    """
    Get a book series by ID.
    """
    try:
        series = await book_series_service.get_series_by_id(
            db=db,
            series_id=series_id,
            include_items=include_items,
            admin_id=current_admin.id,
        )
        return series
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving book series: {str(e)}",
        )


@router.post(
    "/", response_model=BookSeriesResponse, status_code=status.HTTP_201_CREATED
)
async def create_series(
    series_data: BookSeriesCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["book_series:create"])),
):
    """
    Create a new book series.
    """
    try:
        series = await book_series_service.create_series(
            db=db,
            series_data=series_data.model_dump(),
            admin_id=current_admin.id,
        )
        return series
    except ForbiddenException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating book series: {str(e)}",
        )


@router.put("/{series_id}", response_model=BookSeriesResponse)
async def update_series(
    series_id: int = Path(..., description="Series ID"),
    series_data: BookSeriesUpdate = Body(...),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["book_series:update"])),
):
    """
    Update a book series.
    """
    try:
        series = await book_series_service.update_series(
            db=db,
            series_id=series_id,
            series_data=series_data.model_dump(exclude_unset=True),
            admin_id=current_admin.id,
        )
        return series
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ForbiddenException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating book series: {str(e)}",
        )


@router.delete("/{series_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_series(
    series_id: int = Path(..., description="Series ID"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["book_series:delete"])),
):
    """
    Delete a book series.
    """
    try:
        await book_series_service.delete_series(
            db=db,
            series_id=series_id,
            admin_id=current_admin.id,
        )
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting book series: {str(e)}",
        )


@router.get("/{series_id}/books", response_model=BookSeriesItemListResponse)
async def get_series_books(
    series_id: int = Path(..., description="Series ID"),
    skip: int = Query(0, description="Number of records to skip"),
    limit: int = Query(20, description="Max number of records to return"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["book_series:read"])),
):
    """
    Get all books in a series.
    """
    try:
        items = await book_series_service.get_series_items(
            db=db,
            series_id=series_id,
            skip=skip,
            limit=limit,
        )

        total_count = await book_series_service.count_series_items(
            db=db,
            series_id=series_id,
        )

        return BookSeriesItemListResponse(
            items=items,
            total=total_count,
            page=skip // limit + 1 if limit > 0 else 1,
            size=limit,
        )
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving books in series: {str(e)}",
        )


@router.post(
    "/{series_id}/books",
    response_model=BookSeriesItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_book_to_series(
    series_id: int = Path(..., description="Series ID"),
    book_data: BookSeriesItemCreate = Body(...),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["book_series:update"])),
):
    """
    Add a book to a series.
    """
    try:
        book_id = book_data.book_id
        position = book_data.position

        item = await book_series_service.add_book_to_series(
            db=db,
            series_id=series_id,
            book_id=book_id,
            position=position,
            admin_id=current_admin.id,
        )
        return item
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ForbiddenException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error adding book to series: {str(e)}",
        )


@router.delete("/books/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_book_from_series(
    item_id: int = Path(..., description="Series item ID"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["book_series:update"])),
):
    """
    Remove a book from a series.
    """
    try:
        await book_series_service.remove_book_from_series(
            db=db,
            item_id=item_id,
            admin_id=current_admin.id,
        )
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error removing book from series: {str(e)}",
        )


@router.put("/books/{item_id}", response_model=BookSeriesItemResponse)
async def update_series_item(
    item_id: int = Path(..., description="Series item ID"),
    item_data: BookSeriesItemCreate = Body(...),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["book_series:update"])),
):
    """
    Update a book position in a series.
    """
    try:
        item = await book_series_service.update_series_item(
            db=db,
            item_id=item_id,
            item_data=item_data.model_dump(exclude_unset=True),
        )
        return item
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating series item: {str(e)}",
        )


@router.get("/stats", response_model=BookSeriesStatsResponse)
async def get_book_series_statistics(
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["book_series:read", "stats:read"])
    ),
):
    """
    Get book series statistics.
    """
    try:
        stats = await book_series_service.get_book_series_statistics(
            db=db,
            admin_id=current_admin.id,
        )
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving book series statistics: {str(e)}",
        )
