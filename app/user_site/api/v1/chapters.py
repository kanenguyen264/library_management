from typing import Dict, Any, List, Optional
from fastapi import (
    APIRouter,
    Depends,
    Path,
    Query,
    HTTPException,
    status,
    Request,
    Body,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db.session import get_db
from app.user_site.api.deps import (
    get_current_user,
    get_current_active_user,
    get_current_premium_user)
from app.user_site.api.v1 import throttle_requests
from app.user_site.models.user import User
from app.user_site.schemas.chapter import (
    ChapterResponse,
    ChapterDetailResponse,
    ChapterContentResponse,
    ChapterCommentCreate,
    ChapterCommentUpdate,
    ChapterCommentResponse,
    ChapterReadingPosition,
    ChapterProgressResponse,
)
from app.user_site.services.chapter_service import ChapterService
from app.user_site.services.book_service import BookService
from app.user_site.services.user_service import UserService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time
from app.cache.decorators import cache_response, invalidate_cache
from app.security.encryption.field_encryption import decrypt_sensitive_content
from app.security.audit.audit_trails import log_data_operation
from app.core.exceptions import (
    BadRequestException,
    UnauthorizedException,
    ForbiddenException,
    NotFoundException,
    ConflictException,
    ServerException,
)

router = APIRouter()
logger = get_logger("chapter_api")


@router.get("/{chapter_id}", response_model=ChapterDetailResponse)
@track_request_time(endpoint="get_chapter_details")
@cache_response(ttl=600, vary_by=["chapter_id", "current_user.id"])
async def get_chapter_details(
    chapter_id: int = Path(..., gt=0, description="ID của chương sách"),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy thông tin chi tiết của một chương sách.

    - **chapter_id**: ID của chương sách
    """
    chapter_service = ChapterService(db)
    book_service = BookService(db)

    try:
        # Lấy thông tin chương
        chapter = await chapter_service.get_chapter_by_id(chapter_id)

        if not chapter:
            raise NotFoundException(
                detail=f"Không tìm thấy chương với ID: {chapter_id}",
                code="chapter_not_found",
            )

        # Lấy thông tin sách
        book = await book_service.get_book_by_id(chapter.book_id)

        if not book:
            raise NotFoundException(
                detail="Không tìm thấy sách của chương này", code="book_not_found"
            )

        # Kiểm tra quyền truy cập
        # Nếu chương không miễn phí và người dùng không đăng nhập hoặc không phải premium
        if not chapter.is_free:
            # Nếu không có current_user (chưa đăng nhập)
            if not current_user:
                raise UnauthorizedException(
                    detail="Bạn cần đăng nhập để đọc chương này", code="login_required"
                )

            # Nếu chương premium và user không phải premium
            if not current_user.is_premium:
                raise ForbiddenException(
                    detail="Bạn cần nâng cấp tài khoản premium để đọc chương này",
                    code="premium_required",
                )

        # Thêm ghi nhận người dùng đã xem chương này (nếu đã đăng nhập)
        if current_user:
            await chapter_service.record_chapter_view(
                user_id=current_user.id, chapter_id=chapter_id
            )

        return chapter
    except NotFoundException:
        raise
    except UnauthorizedException:
        raise
    except ForbiddenException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin chương sách {chapter_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thông tin chương sách")


@router.get("/{chapter_id}/content", response_model=ChapterContentResponse)
@track_request_time(endpoint="get_chapter_content")
@cache_response(ttl=600, vary_by=["chapter_id", "current_user.id"])
async def get_chapter_content(
    chapter_id: int = Path(..., gt=0, description="ID của chương sách"),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Lấy nội dung của một chương sách.

    - **chapter_id**: ID của chương sách
    """
    chapter_service = ChapterService(db)
    book_service = BookService(db)
    client_ip = request.client.host if request else None
    user_agent = request.headers.get("User-Agent", "") if request else None

    try:
        # Lấy thông tin chương
        chapter = await chapter_service.get_chapter_by_id(chapter_id)

        if not chapter:
            raise NotFoundException(
                detail=f"Không tìm thấy chương với ID: {chapter_id}",
                code="chapter_not_found",
            )

        # Lấy thông tin sách
        book = await book_service.get_book_by_id(chapter.book_id)

        if not book:
            raise NotFoundException(
                detail="Không tìm thấy sách của chương này", code="book_not_found"
            )

        # Kiểm tra quyền truy cập
        # Nếu chương không miễn phí và người dùng không đăng nhập hoặc không phải premium
        if not chapter.is_free:
            # Nếu không có current_user (chưa đăng nhập)
            if not current_user:
                raise UnauthorizedException(
                    detail="Bạn cần đăng nhập để đọc chương này", code="login_required"
                )

            # Nếu chương premium và user không phải premium
            if not current_user.is_premium:
                raise ForbiddenException(
                    detail="Bạn cần nâng cấp tài khoản premium để đọc chương này",
                    code="premium_required",
                )

        # Lấy nội dung chương
        content = await chapter_service.get_chapter_content(chapter_id)

        if not content:
            raise NotFoundException(
                detail="Không tìm thấy nội dung của chương này",
                code="content_not_found",
            )

        # Giải mã nội dung nếu được mã hóa
        if content.is_encrypted:
            content.content = decrypt_sensitive_content(content.content)

        # Ghi log nếu người dùng đã đăng nhập
        if current_user:
            # Cập nhật lịch sử đọc
            await chapter_service.update_reading_history(
                user_id=current_user.id, chapter_id=chapter_id, book_id=chapter.book_id
            )

            # Ghi audit log
            if request:
                await log_data_operation(
                    operation="read",
                    resource_type="chapter",
                    resource_id=str(chapter_id),
                    user_id=str(current_user.id),
                    user_type="user",
                    status="success",
                    ip_address=client_ip,
                    user_agent=user_agent,
                )

        # Tăng số lượt đọc cho chương
        await chapter_service.increment_chapter_views(chapter_id)

        return content
    except NotFoundException:
        raise
    except UnauthorizedException:
        raise
    except ForbiddenException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy nội dung chương sách {chapter_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy nội dung chương sách")


@router.get("/book/{book_id}", response_model=List[ChapterResponse])
@track_request_time(endpoint="get_book_chapters")
@cache_response(ttl=600, vary_by=["book_id", "current_user.id"])
async def get_book_chapters(
    book_id: int = Path(..., gt=0, description="ID của sách"),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách các chương của một sách.

    - **book_id**: ID của sách
    """
    chapter_service = ChapterService(db)
    book_service = BookService(db)

    try:
        # Kiểm tra sách có tồn tại không
        book = await book_service.get_book_by_id(book_id)

        if not book:
            raise NotFoundException(
                detail=f"Không tìm thấy sách với ID: {book_id}", code="book_not_found"
            )

        # Lấy danh sách chương
        chapters = await chapter_service.get_chapters_by_book_id(book_id)

        # Đánh dấu chương nào đã đọc nếu người dùng đã đăng nhập
        if current_user:
            read_chapters = await chapter_service.get_read_chapters(
                user_id=current_user.id, book_id=book_id
            )

            # Đánh dấu các chương đã đọc
            for chapter in chapters:
                chapter.is_read = chapter.id in read_chapters

        # Đối với người dùng chưa đăng nhập hoặc không phải premium
        # Chỉ hiển thị một phần nội dung preview cho các chương không miễn phí
        if not current_user or not current_user.is_premium:
            for chapter in chapters:
                if not chapter.is_free:
                    chapter.preview_available = True

        return chapters
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách chương sách {book_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách chương sách")


@router.post("/{chapter_id}/comments", response_model=ChapterCommentResponse)
@track_request_time(endpoint="add_chapter_comment")
@invalidate_cache(namespace="chapters", tags=["chapter_comments"])
async def add_chapter_comment(
    comment_data: ChapterCommentCreate,
    chapter_id: int = Path(..., gt=0, description="ID của chương sách"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Thêm bình luận cho một chương sách.

    - **chapter_id**: ID của chương sách
    - **content**: Nội dung bình luận
    - **position**: Vị trí trong chương (nếu có)
    - **parent_id**: ID của bình luận cha (nếu là trả lời)
    """
    chapter_service = ChapterService(db)
    client_ip = request.client.host if request else None
    user_agent = request.headers.get("User-Agent", "") if request else None

    try:
        # Giới hạn số lượng bình luận trong 1 giờ
        await throttle_requests(
            "add_comment",
            limit=20,
            period=3600,
            request=request,
            current_user=current_user,
            db=db,
        )

        # Kiểm tra chương có tồn tại không
        chapter = await chapter_service.get_chapter_by_id(chapter_id)

        if not chapter:
            raise NotFoundException(
                detail=f"Không tìm thấy chương với ID: {chapter_id}",
                code="chapter_not_found",
            )

        # Kiểm tra parent_id có hợp lệ không (nếu có)
        if comment_data.parent_id:
            parent_comment = await chapter_service.get_comment_by_id(
                comment_data.parent_id
            )

            if not parent_comment or parent_comment.chapter_id != chapter_id:
                raise BadRequestException(
                    detail="Bình luận cha không tồn tại hoặc không thuộc chương này",
                    field="parent_id",
                    code="invalid_parent_comment",
                )

        # Thêm bình luận
        comment = await chapter_service.add_comment(
            user_id=current_user.id,
            chapter_id=chapter_id,
            content=comment_data.content,
            position=comment_data.position,
            parent_id=comment_data.parent_id,
        )

        # Ghi log
        logger.info(f"Thêm bình luận cho chương {chapter_id}, user: {current_user.id}")

        # Ghi log audit
        if request:
            await log_data_operation(
                operation="create",
                resource_type="chapter_comment",
                resource_id=str(comment.id),
                user_id=str(current_user.id),
                user_type="user",
                status="success",
                ip_address=client_ip,
                user_agent=user_agent,
                changes={"chapter_id": chapter_id, "parent_id": comment_data.parent_id},
            )

        return comment
    except BadRequestException:
        raise
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi thêm bình luận cho chương {chapter_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi thêm bình luận cho chương")


@router.get("/{chapter_id}/comments", response_model=Dict[str, Any])
@track_request_time(endpoint="get_chapter_comments")
@cache_response(ttl=300, vary_by=["chapter_id", "page", "page_size"])
async def get_chapter_comments(
    chapter_id: int = Path(..., gt=0, description="ID của chương sách"),
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    page_size: int = Query(
        20, ge=1, le=100, description="Số lượng bình luận mỗi trang"
    ),
    sort_by: str = Query("created_at", regex="^(created_at|likes)$"),
    sort_desc: bool = Query(True, description="Sắp xếp giảm dần"),
    parent_only: bool = Query(False, description="Chỉ lấy bình luận gốc"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách bình luận của một chương sách.

    - **chapter_id**: ID của chương sách
    - **page**: Trang hiện tại
    - **page_size**: Số lượng bình luận mỗi trang
    - **sort_by**: Sắp xếp theo trường (created_at, likes)
    - **sort_desc**: Sắp xếp giảm dần (True) hoặc tăng dần (False)
    - **parent_only**: Chỉ lấy bình luận gốc (không bao gồm trả lời)
    """
    chapter_service = ChapterService(db)

    try:
        # Kiểm tra chương có tồn tại không
        chapter = await chapter_service.get_chapter_by_id(chapter_id)

        if not chapter:
            raise NotFoundException(
                detail=f"Không tìm thấy chương với ID: {chapter_id}",
                code="chapter_not_found",
            )

        # Tính toán skip từ page và page_size
        skip = (page - 1) * page_size

        # Lấy danh sách bình luận
        comments, total = await chapter_service.get_chapter_comments(
            chapter_id=chapter_id,
            skip=skip,
            limit=page_size,
            sort_by=sort_by,
            sort_desc=sort_desc,
            parent_only=parent_only,
        )

        # Tính toán thông tin phân trang
        total_pages = (total + page_size - 1) // page_size

        # Nếu chỉ lấy bình luận gốc, thì lấy thêm các trả lời cho từng bình luận
        if parent_only and comments:
            for comment in comments:
                replies, _ = await chapter_service.get_comment_replies(
                    comment_id=comment.id, limit=5  # Chỉ lấy 5 trả lời đầu tiên
                )
                comment.replies = replies
                comment.reply_count = await chapter_service.get_reply_count(comment.id)

        return {
            "items": comments,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy bình luận cho chương {chapter_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy bình luận cho chương")


@router.get(
    "/{chapter_id}/comments/{comment_id}/replies", response_model=Dict[str, Any]
)
@track_request_time(endpoint="get_comment_replies")
@cache_response(ttl=300, vary_by=["comment_id", "page", "page_size"])
async def get_comment_replies(
    chapter_id: int,
    comment_id: int,
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    page_size: int = Query(20, ge=1, le=100, description="Số lượng trả lời mỗi trang"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách trả lời cho một bình luận.

    - **chapter_id**: ID của chương sách
    - **comment_id**: ID của bình luận
    - **page**: Trang hiện tại
    - **page_size**: Số lượng trả lời mỗi trang
    """
    chapter_service = ChapterService(db)

    try:
        # Kiểm tra bình luận có tồn tại không và có thuộc chương này không
        comment = await chapter_service.get_comment_by_id(comment_id)

        if not comment or comment.chapter_id != chapter_id:
            raise NotFoundException(
                detail="Không tìm thấy bình luận hoặc bình luận không thuộc chương này",
                code="comment_not_found",
            )

        # Tính toán skip từ page và page_size
        skip = (page - 1) * page_size

        # Lấy danh sách trả lời
        replies, total = await chapter_service.get_comment_replies(
            comment_id=comment_id, skip=skip, limit=page_size
        )

        # Tính toán thông tin phân trang
        total_pages = (total + page_size - 1) // page_size

        return {
            "items": replies,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "parent_comment": comment,
        }
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy trả lời cho bình luận {comment_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy trả lời cho bình luận")


@router.put(
    "/{chapter_id}/comments/{comment_id}", response_model=ChapterCommentResponse
)
@track_request_time(endpoint="update_comment")
@invalidate_cache(namespace="chapters", tags=["chapter_comments"])
async def update_comment(
    comment_data: ChapterCommentUpdate,
    chapter_id: int,
    comment_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Cập nhật nội dung bình luận.

    - **chapter_id**: ID của chương sách
    - **comment_id**: ID của bình luận
    - **content**: Nội dung bình luận mới
    """
    chapter_service = ChapterService(db)
    client_ip = request.client.host if request else None
    user_agent = request.headers.get("User-Agent", "") if request else None

    try:
        # Kiểm tra bình luận có tồn tại không và có thuộc chương này không
        comment = await chapter_service.get_comment_by_id(comment_id)

        if not comment or comment.chapter_id != chapter_id:
            raise NotFoundException(
                detail="Không tìm thấy bình luận hoặc bình luận không thuộc chương này",
                code="comment_not_found",
            )

        # Kiểm tra quyền sở hữu
        if comment.user_id != current_user.id and not current_user.is_admin:
            raise ForbiddenException(
                detail="Bạn không có quyền cập nhật bình luận này", code="not_owner"
            )

        # Cập nhật bình luận
        updated_comment = await chapter_service.update_comment(
            comment_id=comment_id, content=comment_data.content
        )

        # Ghi log
        logger.info(
            f"Cập nhật bình luận {comment_id} cho chương {chapter_id}, user: {current_user.id}"
        )

        # Ghi log audit
        if request:
            await log_data_operation(
                operation="update",
                resource_type="chapter_comment",
                resource_id=str(comment_id),
                user_id=str(current_user.id),
                user_type="user",
                status="success",
                ip_address=client_ip,
                user_agent=user_agent,
            )

        return updated_comment
    except NotFoundException:
        raise
    except ForbiddenException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật bình luận {comment_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi cập nhật bình luận")


@router.delete(
    "/{chapter_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT
)
@track_request_time(endpoint="delete_comment")
@invalidate_cache(namespace="chapters", tags=["chapter_comments"])
async def delete_comment(
    chapter_id: int,
    comment_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Xóa bình luận.

    - **chapter_id**: ID của chương sách
    - **comment_id**: ID của bình luận
    """
    chapter_service = ChapterService(db)
    client_ip = request.client.host if request else None
    user_agent = request.headers.get("User-Agent", "") if request else None

    try:
        # Kiểm tra bình luận có tồn tại không và có thuộc chương này không
        comment = await chapter_service.get_comment_by_id(comment_id)

        if not comment or comment.chapter_id != chapter_id:
            raise NotFoundException(
                detail="Không tìm thấy bình luận hoặc bình luận không thuộc chương này",
                code="comment_not_found",
            )

        # Kiểm tra quyền sở hữu
        if comment.user_id != current_user.id and not current_user.is_admin:
            raise ForbiddenException(
                detail="Bạn không có quyền xóa bình luận này", code="not_owner"
            )

        # Xóa bình luận
        await chapter_service.delete_comment(comment_id)

        # Ghi log
        logger.info(
            f"Xóa bình luận {comment_id} cho chương {chapter_id}, user: {current_user.id}"
        )

        # Ghi log audit
        if request:
            await log_data_operation(
                operation="delete",
                resource_type="chapter_comment",
                resource_id=str(comment_id),
                user_id=str(current_user.id),
                user_type="user",
                status="success",
                ip_address=client_ip,
                user_agent=user_agent,
            )

        return None
    except NotFoundException:
        raise
    except ForbiddenException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa bình luận {comment_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi xóa bình luận")


@router.post(
    "/{chapter_id}/like-comment/{comment_id}", status_code=status.HTTP_204_NO_CONTENT
)
@track_request_time(endpoint="like_comment")
@invalidate_cache(namespace="chapters", tags=["chapter_comments"])
async def like_comment(
    chapter_id: int,
    comment_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Thích một bình luận.

    - **chapter_id**: ID của chương sách
    - **comment_id**: ID của bình luận
    """
    chapter_service = ChapterService(db)

    try:
        # Kiểm tra bình luận có tồn tại không và có thuộc chương này không
        comment = await chapter_service.get_comment_by_id(comment_id)

        if not comment or comment.chapter_id != chapter_id:
            raise NotFoundException(
                detail="Không tìm thấy bình luận hoặc bình luận không thuộc chương này",
                code="comment_not_found",
            )

        # Thích bình luận
        await chapter_service.like_comment(
            user_id=current_user.id, comment_id=comment_id
        )

        return None
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi thích bình luận {comment_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi thích bình luận")


@router.post(
    "/{chapter_id}/unlike-comment/{comment_id}", status_code=status.HTTP_204_NO_CONTENT
)
@track_request_time(endpoint="unlike_comment")
@invalidate_cache(namespace="chapters", tags=["chapter_comments"])
async def unlike_comment(
    chapter_id: int,
    comment_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Bỏ thích một bình luận.

    - **chapter_id**: ID của chương sách
    - **comment_id**: ID của bình luận
    """
    chapter_service = ChapterService(db)

    try:
        # Kiểm tra bình luận có tồn tại không và có thuộc chương này không
        comment = await chapter_service.get_comment_by_id(comment_id)

        if not comment or comment.chapter_id != chapter_id:
            raise NotFoundException(
                detail="Không tìm thấy bình luận hoặc bình luận không thuộc chương này",
                code="comment_not_found",
            )

        # Bỏ thích bình luận
        await chapter_service.unlike_comment(
            user_id=current_user.id, comment_id=comment_id
        )

        return None
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi bỏ thích bình luận {comment_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi bỏ thích bình luận")


@router.post("/{chapter_id}/reading-position", response_model=ChapterProgressResponse)
@track_request_time(endpoint="save_reading_position")
async def save_reading_position(
    position_data: ChapterReadingPosition,
    chapter_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lưu vị trí đọc trong chương.

    - **chapter_id**: ID của chương sách
    - **position**: Vị trí đọc (phần trăm)
    - **scroll_position**: Vị trí cuộn trang
    - **last_paragraph**: ID của đoạn văn cuối cùng đã đọc
    """
    chapter_service = ChapterService(db)

    try:
        # Kiểm tra chương có tồn tại không
        chapter = await chapter_service.get_chapter_by_id(chapter_id)

        if not chapter:
            raise NotFoundException(
                detail=f"Không tìm thấy chương với ID: {chapter_id}",
                code="chapter_not_found",
            )

        # Lưu vị trí đọc
        progress = await chapter_service.save_reading_position(
            user_id=current_user.id,
            chapter_id=chapter_id,
            book_id=chapter.book_id,
            position=position_data.position,
            scroll_position=position_data.scroll_position,
            last_paragraph=position_data.last_paragraph,
        )

        # Đánh dấu chương đã đọc nếu đã đọc hơn 80%
        if position_data.position >= 80:
            await chapter_service.mark_chapter_as_read(
                user_id=current_user.id, chapter_id=chapter_id
            )

        return progress
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lưu vị trí đọc cho chương {chapter_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lưu vị trí đọc")


@router.get("/{chapter_id}/reading-position", response_model=ChapterProgressResponse)
@track_request_time(endpoint="get_reading_position")
@cache_response(ttl=300, vary_by=["chapter_id", "current_user.id"])
async def get_reading_position(
    chapter_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy vị trí đọc trong chương.

    - **chapter_id**: ID của chương sách
    """
    chapter_service = ChapterService(db)

    try:
        # Kiểm tra chương có tồn tại không
        chapter = await chapter_service.get_chapter_by_id(chapter_id)

        if not chapter:
            raise NotFoundException(
                detail=f"Không tìm thấy chương với ID: {chapter_id}",
                code="chapter_not_found",
            )

        # Lấy vị trí đọc
        progress = await chapter_service.get_reading_position(
            user_id=current_user.id, chapter_id=chapter_id
        )

        if not progress:
            # Trả về giá trị mặc định nếu chưa có vị trí đọc
            return ChapterProgressResponse(
                user_id=current_user.id,
                chapter_id=chapter_id,
                book_id=chapter.book_id,
                position=0,
                scroll_position=0,
                last_paragraph="",
                updated_at=None,
            )

        return progress
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy vị trí đọc cho chương {chapter_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy vị trí đọc")
