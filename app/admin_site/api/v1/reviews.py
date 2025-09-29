from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status, Body
from sqlalchemy.orm import Session
from datetime import datetime

from app.common.db.session import get_db
from app.admin_site.api.deps import get_current_admin, check_admin_permissions
from app.user_site.models.user import User
from app.admin_site.services import review_service
from app.user_site.schemas.review import (
    ReviewCreate,
    ReviewUpdate,
    ReviewResponse,
    ReviewListResponse,
    ReviewStatsResponse,
    ReviewLikeResponse,
    ReviewStatus,
)
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    BadRequestException,
)

router = APIRouter()


@router.get("/", response_model=ReviewListResponse)
async def get_reviews(
    skip: int = Query(0, description="Number of records to skip"),
    limit: int = Query(100, description="Max number of records to return"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    book_id: Optional[int] = Query(None, description="Filter by book ID"),
    status: Optional[ReviewStatus] = Query(None, description="Filter by status"),
    rating_min: Optional[int] = Query(None, description="Minimum rating (1-5)"),
    rating_max: Optional[int] = Query(None, description="Maximum rating (1-5)"),
    from_date: Optional[datetime] = Query(None, description="Filter from date"),
    to_date: Optional[datetime] = Query(None, description="Filter to date"),
    search: Optional[str] = Query(None, description="Search in content"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_desc: bool = Query(True, description="Sort in descending order"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["review:read", "review:list"])
    ),
):
    """
    Get list of reviews with various filtering options.
    """
    try:
        reviews = await review_service.get_all_reviews(
            db=db,
            skip=skip,
            limit=limit,
            user_id=user_id,
            book_id=book_id,
            status=status,
            rating_min=rating_min,
            rating_max=rating_max,
            from_date=from_date,
            to_date=to_date,
            search=search,
            sort_by=sort_by,
            sort_desc=sort_desc,
            admin_id=current_admin.id,
        )

        total_count = await review_service.count_reviews(
            db=db,
            user_id=user_id,
            book_id=book_id,
            status=status,
            rating_min=rating_min,
            rating_max=rating_max,
            from_date=from_date,
            to_date=to_date,
            search=search,
        )

        return ReviewListResponse(
            items=reviews,
            total=total_count,
            page=skip // limit + 1 if limit > 0 else 1,
            size=limit,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving reviews: {str(e)}",
        )


@router.get("/stats", response_model=ReviewStatsResponse)
async def get_review_statistics(
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["review:read", "stats:read"])
    ),
):
    """
    Get review statistics.
    """
    try:
        stats = await review_service.get_review_statistics(
            db=db,
            admin_id=current_admin.id,
        )
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving review statistics: {str(e)}",
        )


@router.get("/popular", response_model=List[ReviewResponse])
async def get_popular_reviews(
    limit: int = Query(10, description="Number of reviews to return"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["review:read"])),
):
    """
    Get most popular reviews based on likes.
    """
    try:
        reviews = await review_service.get_popular_reviews(db=db, limit=limit)
        return reviews
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving popular reviews: {str(e)}",
        )


@router.get("/recent", response_model=List[ReviewResponse])
async def get_recent_reviews(
    limit: int = Query(10, description="Number of reviews to return"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["review:read"])),
):
    """
    Get most recent reviews.
    """
    try:
        reviews = await review_service.get_recent_reviews(db=db, limit=limit)
        return reviews
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving recent reviews: {str(e)}",
        )


@router.get("/pending", response_model=List[ReviewResponse])
async def get_pending_reviews(
    limit: int = Query(10, description="Number of reviews to return"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["review:read", "review:moderate"])
    ),
):
    """
    Get reviews pending moderation.
    """
    try:
        reviews = await review_service.get_pending_reviews(db=db, limit=limit)
        return reviews
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving pending reviews: {str(e)}",
        )


@router.get("/{review_id}", response_model=ReviewResponse)
async def get_review(
    review_id: int = Path(..., description="Review ID"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["review:read"])),
):
    """
    Get a review by ID.
    """
    try:
        review = await review_service.get_review_by_id(
            db=db,
            review_id=review_id,
            admin_id=current_admin.id,
        )
        return review
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving review: {str(e)}",
        )


@router.get("/user/{user_id}", response_model=List[ReviewResponse])
async def get_user_reviews(
    user_id: int = Path(..., description="User ID"),
    skip: int = Query(0, description="Number of records to skip"),
    limit: int = Query(20, description="Max number of records to return"),
    status: Optional[ReviewStatus] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["review:read"])),
):
    """
    Get reviews by a specific user.
    """
    try:
        reviews = await review_service.get_user_reviews(
            db=db,
            user_id=user_id,
            skip=skip,
            limit=limit,
            status=status,
        )
        return reviews
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving user reviews: {str(e)}",
        )


@router.get("/book/{book_id}", response_model=List[ReviewResponse])
async def get_book_reviews(
    book_id: int = Path(..., description="Book ID"),
    skip: int = Query(0, description="Number of records to skip"),
    limit: int = Query(20, description="Max number of records to return"),
    status: Optional[ReviewStatus] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["review:read"])),
):
    """
    Get reviews for a specific book.
    """
    try:
        reviews = await review_service.get_book_reviews(
            db=db,
            book_id=book_id,
            skip=skip,
            limit=limit,
            status=status,
        )
        return reviews
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving book reviews: {str(e)}",
        )


@router.post("/", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
async def create_review(
    review_data: ReviewCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["review:create"])),
):
    """
    Create a new review.
    """
    try:
        review = await review_service.create_review(
            db=db,
            review_data=review_data.model_dump(),
            admin_id=current_admin.id,
        )
        return review
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except BadRequestException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating review: {str(e)}",
        )


@router.put("/{review_id}", response_model=ReviewResponse)
async def update_review(
    review_id: int = Path(..., description="Review ID"),
    review_data: ReviewUpdate = Body(...),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["review:update"])),
):
    """
    Update a review.
    """
    try:
        review = await review_service.update_review(
            db=db,
            review_id=review_id,
            review_data=review_data.model_dump(exclude_unset=True),
            admin_id=current_admin.id,
        )
        return review
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BadRequestException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating review: {str(e)}",
        )


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review(
    review_id: int = Path(..., description="Review ID"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["review:delete"])),
):
    """
    Delete a review.
    """
    try:
        await review_service.delete_review(
            db=db,
            review_id=review_id,
            admin_id=current_admin.id,
        )
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting review: {str(e)}",
        )


@router.post("/{review_id}/publish", response_model=ReviewResponse)
async def publish_review(
    review_id: int = Path(..., description="Review ID"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["review:update", "review:moderate"])
    ),
):
    """
    Publish a pending review.
    """
    try:
        review = await review_service.change_review_status(
            db=db,
            review_id=review_id,
            status=ReviewStatus.PUBLISHED,
            admin_id=current_admin.id,
        )
        return review
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error publishing review: {str(e)}",
        )


@router.post("/{review_id}/reject", response_model=ReviewResponse)
async def reject_review(
    review_id: int = Path(..., description="Review ID"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["review:update", "review:moderate"])
    ),
):
    """
    Reject a pending review.
    """
    try:
        review = await review_service.change_review_status(
            db=db,
            review_id=review_id,
            status=ReviewStatus.REJECTED,
            admin_id=current_admin.id,
        )
        return review
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error rejecting review: {str(e)}",
        )


@router.post("/{review_id}/status", response_model=ReviewResponse)
async def change_review_status(
    review_id: int = Path(..., description="Review ID"),
    status: ReviewStatus = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["review:update", "review:moderate"])
    ),
):
    """
    Change review status.
    """
    try:
        review = await review_service.change_review_status(
            db=db,
            review_id=review_id,
            status=status,
            admin_id=current_admin.id,
        )
        return review
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error changing review status: {str(e)}",
        )


@router.get("/{review_id}/likes", response_model=List[ReviewLikeResponse])
async def get_review_likes(
    review_id: int = Path(..., description="Review ID"),
    skip: int = Query(0, description="Number of records to skip"),
    limit: int = Query(20, description="Max number of records to return"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["review:read"])),
):
    """
    Get users who liked a review.
    """
    try:
        likes = await review_service.get_review_likes(
            db=db,
            review_id=review_id,
            skip=skip,
            limit=limit,
        )
        return likes
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving review likes: {str(e)}",
        )
