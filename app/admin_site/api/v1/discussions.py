from typing import List, Optional, Dict, Any
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Path,
    Body,
    Request,
    status,
)
from sqlalchemy.orm import Session
from datetime import datetime, date

from app.common.db.session import get_db
from app.user_site.schemas.discussion import (
    DiscussionCreate,
    DiscussionUpdate,
    DiscussionResponse as DiscussionInfo,
    DiscussionListResponse as DiscussionList,
    DiscussionStatistics,
    DiscussionCommentCreate,
    DiscussionCommentUpdate,
    DiscussionCommentInfo,
)
from app.admin_site.services import discussion_service
from app.admin_site.api.deps import secure_admin_access
from app.security.audit.log_admin_action import log_admin_action
from app.performance.profiling.api_profiler import profile_endpoint
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    BadRequestException,
)
from app.cache.decorators import cached
from app.logging.setup import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/", response_model=DiscussionList)
@profile_endpoint(name="admin:discussions:list")
@cached(ttl=300, namespace="admin:discussions", key_prefix="discussions_list")
async def get_discussions(
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    size: int = Query(10, ge=1, le=100, description="Số lượng mỗi trang"),
    book_id: Optional[int] = Query(None, description="Lọc theo ID sách"),
    chapter_id: Optional[int] = Query(None, description="Lọc theo ID chương"),
    user_id: Optional[int] = Query(None, description="Lọc theo ID người dùng"),
    is_pinned: Optional[bool] = Query(None, description="Lọc theo trạng thái ghim"),
    sort_by: str = Query("created_at", description="Sắp xếp theo trường"),
    sort_desc: bool = Query(True, description="Sắp xếp giảm dần"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["discussions:read"])),
    request: Request = None,
):
    """
    Lấy danh sách thảo luận với các tùy chọn lọc và phân trang.

    - **page**: Trang hiện tại
    - **size**: Số lượng mỗi trang
    - **book_id**: Lọc theo ID sách
    - **chapter_id**: Lọc theo ID chương
    - **user_id**: Lọc theo ID người dùng
    - **is_pinned**: Lọc theo trạng thái ghim
    - **sort_by**: Sắp xếp theo trường
    - **sort_desc**: Sắp xếp giảm dần
    """
    try:
        skip = (page - 1) * size

        discussions = await discussion_service.get_all_discussions(
            db=db,
            skip=skip,
            limit=size,
            book_id=book_id,
            chapter_id=chapter_id,
            user_id=user_id,
            is_pinned=is_pinned,
            sort_by=sort_by,
            sort_desc=sort_desc,
            admin_id=admin.get("id"),
        )

        total = await discussion_service.count_discussions(
            db=db,
            book_id=book_id,
            chapter_id=chapter_id,
            user_id=user_id,
            is_pinned=is_pinned,
        )

        pages = (total + size - 1) // size if size > 0 else 0

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem danh sách thảo luận (trang {page}, số lượng {size})"
        )

        return {
            "items": discussions,
            "total": total,
            "page": page,
            "size": size,
            "pages": pages,
        }
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách thảo luận: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy danh sách thảo luận: " + str(e),
        )


@router.get("/statistics", response_model=DiscussionStatistics)
@profile_endpoint(name="admin:discussions:statistics")
@cached(ttl=600, namespace="admin:discussions", key_prefix="discussions_statistics")
async def get_discussion_statistics(
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["discussions:read", "statistics:read"])),
    request: Request = None,
):
    """
    Lấy thống kê tổng quan về thảo luận.
    """
    try:
        stats = await discussion_service.get_discussion_statistics(
            db=db, admin_id=admin.get("id")
        )

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem thống kê thảo luận"
        )

        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê thảo luận: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy thống kê thảo luận: " + str(e),
        )


@router.get("/{discussion_id}", response_model=DiscussionInfo)
@profile_endpoint(name="admin:discussions:detail")
@cached(ttl=300, namespace="admin:discussions", key_prefix="discussion_detail")
async def get_discussion_detail(
    discussion_id: int = Path(..., description="ID của thảo luận cần lấy thông tin"),
    with_relations: bool = Query(False, description="Bao gồm các mối quan hệ"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["discussions:read"])),
    request: Request = None,
):
    """
    Lấy thông tin chi tiết của một thảo luận theo ID.

    - **discussion_id**: ID của thảo luận cần lấy thông tin
    - **with_relations**: Bao gồm các mối quan hệ liên quan
    """
    try:
        discussion = await discussion_service.get_discussion_by_id(
            db=db,
            discussion_id=discussion_id,
            with_relations=with_relations,
            admin_id=admin.get("id"),
        )

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem chi tiết thảo luận ID: {discussion_id}"
        )

        return discussion
    except NotFoundException as e:
        logger.warning(f"Không tìm thấy thảo luận: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi lấy chi tiết thảo luận: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy chi tiết thảo luận: " + str(e),
        )


@router.get("/{discussion_id}/comments", response_model=List[DiscussionCommentInfo])
@profile_endpoint(name="admin:discussions:comments")
@cached(ttl=300, namespace="admin:discussions", key_prefix="discussion_comments")
async def get_discussion_comments(
    discussion_id: int = Path(..., description="ID của thảo luận"),
    parent_id: Optional[int] = Query(None, description="ID của bình luận cha"),
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    size: int = Query(20, ge=1, le=100, description="Số lượng mỗi trang"),
    sort_by: str = Query("created_at", description="Sắp xếp theo trường"),
    sort_desc: bool = Query(False, description="Sắp xếp giảm dần"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["discussions:read"])),
    request: Request = None,
):
    """
    Lấy danh sách bình luận của một thảo luận.

    - **discussion_id**: ID của thảo luận
    - **parent_id**: ID của bình luận cha (nếu là phản hồi)
    - **page**: Trang hiện tại
    - **size**: Số lượng mỗi trang
    - **sort_by**: Sắp xếp theo trường
    - **sort_desc**: Sắp xếp giảm dần
    """
    try:
        skip = (page - 1) * size

        comments = await discussion_service.get_comments(
            db=db,
            discussion_id=discussion_id,
            parent_id=parent_id,
            skip=skip,
            limit=size,
            sort_by=sort_by,
            sort_desc=sort_desc,
        )

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem bình luận của thảo luận ID: {discussion_id}"
        )

        return comments
    except NotFoundException as e:
        logger.warning(f"Không tìm thấy thảo luận: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi lấy bình luận của thảo luận: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy bình luận của thảo luận: " + str(e),
        )


@router.post("/", response_model=DiscussionInfo, status_code=status.HTTP_201_CREATED)
@profile_endpoint(name="admin:discussions:create")
@log_admin_action(
    action="create", resource_type="discussion", description="Tạo thảo luận mới"
)
async def create_discussion(
    discussion_data: DiscussionCreate,
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["discussions:create"])),
    request: Request = None,
):
    """
    Tạo thảo luận mới.

    - **discussion_data**: Dữ liệu thảo luận cần tạo
    """
    try:
        discussion = await discussion_service.create_discussion(
            db=db, discussion_data=discussion_data.model_dump(), admin_id=admin.get("id")
        )

        logger.info(f"Admin {admin.get('username', 'unknown')} đã tạo thảo luận mới")

        return discussion
    except NotFoundException as e:
        logger.warning(f"Không tìm thấy sách/chương/người dùng: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BadRequestException as e:
        logger.warning(f"Dữ liệu không hợp lệ khi tạo thảo luận: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi tạo thảo luận mới: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi tạo thảo luận mới: " + str(e),
        )


@router.post(
    "/{discussion_id}/comments",
    response_model=DiscussionCommentInfo,
    status_code=status.HTTP_201_CREATED,
)
@profile_endpoint(name="admin:discussions:comment_create")
@log_admin_action(
    action="create",
    resource_type="discussion_comment",
    description="Tạo bình luận mới cho thảo luận",
)
async def create_discussion_comment(
    discussion_id: int = Path(..., description="ID của thảo luận"),
    comment_data: DiscussionCommentCreate = Body(
        ..., description="Dữ liệu bình luận cần tạo"
    ),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["discussions:comment"])),
    request: Request = None,
):
    """
    Tạo bình luận mới cho thảo luận.

    - **discussion_id**: ID của thảo luận
    - **comment_data**: Dữ liệu bình luận cần tạo
    """
    try:
        comment = await discussion_service.create_comment(
            db=db,
            discussion_id=discussion_id,
            comment_data=comment_data.model_dump(),
            admin_id=admin.get("id"),
        )

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã tạo bình luận mới cho thảo luận ID: {discussion_id}"
        )

        return comment
    except NotFoundException as e:
        logger.warning(f"Không tìm thấy thảo luận: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BadRequestException as e:
        logger.warning(f"Dữ liệu không hợp lệ khi tạo bình luận: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi tạo bình luận: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi tạo bình luận: " + str(e),
        )


@router.put(
    "/{discussion_id}/comments/{comment_id}", response_model=DiscussionCommentInfo
)
@profile_endpoint(name="admin:discussions:comment_update")
@log_admin_action(
    action="update",
    resource_type="discussion_comment",
    description="Cập nhật bình luận",
)
async def update_discussion_comment(
    discussion_id: int = Path(..., description="ID của thảo luận"),
    comment_id: int = Path(..., description="ID của bình luận"),
    comment_data: DiscussionCommentUpdate = Body(..., description="Dữ liệu cập nhật"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["discussions:comment"])),
    request: Request = None,
):
    """
    Cập nhật bình luận.

    - **discussion_id**: ID của thảo luận
    - **comment_id**: ID của bình luận
    - **comment_data**: Dữ liệu cập nhật
    """
    try:
        comment = await discussion_service.update_comment(
            db=db,
            discussion_id=discussion_id,
            comment_id=comment_id,
            comment_data=comment_data.model_dump(exclude_unset=True),
            admin_id=admin.get("id"),
        )

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã cập nhật bình luận ID: {comment_id} trong thảo luận ID: {discussion_id}"
        )

        return comment
    except NotFoundException as e:
        logger.warning(f"Không tìm thấy thảo luận hoặc bình luận: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật bình luận: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi cập nhật bình luận: " + str(e),
        )


@router.delete(
    "/{discussion_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT
)
@profile_endpoint(name="admin:discussions:comment_delete")
@log_admin_action(
    action="delete", resource_type="discussion_comment", description="Xóa bình luận"
)
async def delete_discussion_comment(
    discussion_id: int = Path(..., description="ID của thảo luận"),
    comment_id: int = Path(..., description="ID của bình luận"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["discussions:comment"])),
    request: Request = None,
):
    """
    Xóa bình luận.

    - **discussion_id**: ID của thảo luận
    - **comment_id**: ID của bình luận
    """
    try:
        await discussion_service.delete_comment(
            db=db,
            discussion_id=discussion_id,
            comment_id=comment_id,
            admin_id=admin.get("id"),
        )

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xóa bình luận ID: {comment_id} trong thảo luận ID: {discussion_id}"
        )

        return None
    except NotFoundException as e:
        logger.warning(f"Không tìm thấy thảo luận hoặc bình luận: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi xóa bình luận: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi xóa bình luận: " + str(e),
        )


@router.put("/{discussion_id}", response_model=DiscussionInfo)
@profile_endpoint(name="admin:discussions:update")
@log_admin_action(
    action="update",
    resource_type="discussion",
    description="Cập nhật thông tin thảo luận",
)
async def update_discussion(
    discussion_id: int = Path(..., description="ID của thảo luận cần cập nhật"),
    discussion_data: DiscussionUpdate = Body(..., description="Dữ liệu cập nhật"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["discussions:update"])),
    request: Request = None,
):
    """
    Cập nhật thông tin thảo luận.

    - **discussion_id**: ID của thảo luận cần cập nhật
    - **discussion_data**: Dữ liệu cập nhật
    """
    try:
        discussion = await discussion_service.update_discussion(
            db=db,
            discussion_id=discussion_id,
            discussion_data=discussion_data.model_dump(exclude_unset=True),
            admin_id=admin.get("id"),
        )

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã cập nhật thông tin thảo luận ID: {discussion_id}"
        )

        return discussion
    except NotFoundException as e:
        logger.warning(f"Không tìm thấy thảo luận: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật thông tin thảo luận: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi cập nhật thông tin thảo luận: " + str(e),
        )


@router.put("/{discussion_id}/pin", response_model=DiscussionInfo)
@profile_endpoint(name="admin:discussions:pin")
@log_admin_action(
    action="update", resource_type="discussion_pin", description="Ghim thảo luận"
)
async def pin_discussion(
    discussion_id: int = Path(..., description="ID của thảo luận cần ghim"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["discussions:update"])),
    request: Request = None,
):
    """
    Ghim thảo luận.

    - **discussion_id**: ID của thảo luận cần ghim
    """
    try:
        discussion = await discussion_service.pin_discussion(
            db=db, discussion_id=discussion_id, admin_id=admin.get("id")
        )

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã ghim thảo luận ID: {discussion_id}"
        )

        return discussion
    except NotFoundException as e:
        logger.warning(f"Không tìm thấy thảo luận: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi ghim thảo luận: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi ghim thảo luận: " + str(e),
        )


@router.put("/{discussion_id}/unpin", response_model=DiscussionInfo)
@profile_endpoint(name="admin:discussions:unpin")
@log_admin_action(
    action="update", resource_type="discussion_unpin", description="Bỏ ghim thảo luận"
)
async def unpin_discussion(
    discussion_id: int = Path(..., description="ID của thảo luận cần bỏ ghim"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["discussions:update"])),
    request: Request = None,
):
    """
    Bỏ ghim thảo luận.

    - **discussion_id**: ID của thảo luận cần bỏ ghim
    """
    try:
        discussion = await discussion_service.unpin_discussion(
            db=db, discussion_id=discussion_id, admin_id=admin.get("id")
        )

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã bỏ ghim thảo luận ID: {discussion_id}"
        )

        return discussion
    except NotFoundException as e:
        logger.warning(f"Không tìm thấy thảo luận: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi bỏ ghim thảo luận: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi bỏ ghim thảo luận: " + str(e),
        )


@router.delete("/{discussion_id}", status_code=status.HTTP_204_NO_CONTENT)
@profile_endpoint(name="admin:discussions:delete")
@log_admin_action(
    action="delete", resource_type="discussion", description="Xóa thảo luận"
)
async def delete_discussion(
    discussion_id: int = Path(..., description="ID của thảo luận cần xóa"),
    with_comments: bool = Query(True, description="Xóa cả bình luận liên quan"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["discussions:delete"])),
    request: Request = None,
):
    """
    Xóa thảo luận.

    - **discussion_id**: ID của thảo luận cần xóa
    - **with_comments**: Xóa cả bình luận liên quan
    """
    try:
        await discussion_service.delete_discussion(
            db=db,
            discussion_id=discussion_id,
            with_comments=with_comments,
            admin_id=admin.get("id"),
        )

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xóa thảo luận ID: {discussion_id}"
        )

        return None
    except NotFoundException as e:
        logger.warning(f"Không tìm thấy thảo luận: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi xóa thảo luận: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi xóa thảo luận: " + str(e),
        )


@router.get("/book/{book_id}/summary", response_model=DiscussionStatistics)
@profile_endpoint(name="admin:discussions:book_summary")
@cached(ttl=600, namespace="admin:discussions", key_prefix="book_discussions_summary")
async def get_book_discussions_summary(
    book_id: int = Path(..., description="ID của sách"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["discussions:read", "statistics:read"])),
    request: Request = None,
):
    """
    Lấy thống kê tổng quan về các thảo luận của một sách.

    - **book_id**: ID của sách
    """
    try:
        stats = await discussion_service.get_book_discussions_statistics(
            db=db, book_id=book_id
        )

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem thống kê thảo luận của sách ID: {book_id}"
        )

        return stats
    except NotFoundException as e:
        logger.warning(f"Không tìm thấy sách: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê thảo luận của sách: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy thống kê thảo luận của sách: " + str(e),
        )


@router.get("/user/{user_id}/summary", response_model=DiscussionStatistics)
@profile_endpoint(name="admin:discussions:user_summary")
@cached(ttl=600, namespace="admin:discussions", key_prefix="user_discussions_summary")
async def get_user_discussions_summary(
    user_id: int = Path(..., description="ID của người dùng"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["discussions:read", "statistics:read"])),
    request: Request = None,
):
    """
    Lấy thống kê tổng quan về các thảo luận của một người dùng.

    - **user_id**: ID của người dùng
    """
    try:
        stats = await discussion_service.get_user_discussions_statistics(
            db=db, user_id=user_id
        )

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem thống kê thảo luận của người dùng ID: {user_id}"
        )

        return stats
    except NotFoundException as e:
        logger.warning(f"Không tìm thấy người dùng: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê thảo luận của người dùng: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy thống kê thảo luận của người dùng: " + str(e),
        )


@router.get("/trending", response_model=List[DiscussionInfo])
@profile_endpoint(name="admin:discussions:trending")
@cached(ttl=600, namespace="admin:discussions", key_prefix="trending_discussions")
async def get_trending_discussions(
    limit: int = Query(10, ge=1, le=50, description="Số lượng tối đa"),
    period_days: int = Query(7, ge=1, le=90, description="Khoảng thời gian (ngày)"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["discussions:read"])),
    request: Request = None,
):
    """
    Lấy danh sách thảo luận thịnh hành.

    - **limit**: Số lượng thảo luận tối đa trả về
    - **period_days**: Khoảng thời gian tính xu hướng (ngày)
    """
    try:
        discussions = await discussion_service.get_trending_discussions(
            db=db, limit=limit, period_days=period_days
        )

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem danh sách thảo luận thịnh hành"
        )

        return discussions
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách thảo luận thịnh hành: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy danh sách thảo luận thịnh hành: " + str(e),
        )


@router.get("/recent", response_model=List[DiscussionInfo])
@profile_endpoint(name="admin:discussions:recent")
@cached(ttl=600, namespace="admin:discussions", key_prefix="recent_discussions")
async def get_recent_discussions(
    limit: int = Query(10, ge=1, le=50, description="Số lượng tối đa"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["discussions:read"])),
    request: Request = None,
):
    """
    Lấy danh sách thảo luận gần đây nhất.

    - **limit**: Số lượng thảo luận tối đa trả về
    """
    try:
        discussions = await discussion_service.get_recent_discussions(
            db=db, limit=limit
        )

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem danh sách thảo luận gần đây"
        )

        return discussions
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách thảo luận gần đây: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy danh sách thảo luận gần đây: " + str(e),
        )
