from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from app.admin_site.models import ContentApprovalQueue
from app.admin_site.schemas.content_approval import (
    ContentApprovalCreate,
    ContentApprovalUpdate,
)
from app.admin_site.repositories.content_approval_repo import ContentApprovalRepository
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ServerException,
    ConflictException,
)
from app.cache.decorators import cached, invalidate_cache
from app.logging.setup import get_logger
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

logger = get_logger(__name__)


@cached(ttl=300, namespace="admin:content_approvals", tags=["content_approvals"])
def get_all_content_approvals(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    content_type: Optional[str] = None,
    status: Optional[str] = None,
    submitted_by: Optional[int] = None,
    reviewer_id: Optional[int] = None,
    order_by: str = "created_at",
    order_desc: bool = True,
    admin_id: Optional[int] = None,
) -> List[ContentApprovalQueue]:
    """
    Lấy danh sách yêu cầu phê duyệt nội dung.

    Args:
        db: Database session
        skip: Số lượng bản ghi bỏ qua
        limit: Số lượng bản ghi tối đa
        content_type: Lọc theo loại nội dung
        status: Lọc theo trạng thái
        submitted_by: Lọc theo người gửi
        reviewer_id: Lọc theo người duyệt
        order_by: Sắp xếp theo trường
        order_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách yêu cầu phê duyệt
    """
    try:
        approvals = ContentApprovalRepository.get_all(
            db,
            skip,
            limit,
            content_type,
            status,
            submitted_by,
            reviewer_id,
            order_by,
            order_desc,
        )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="CONTENT_APPROVAL",
                        entity_id=0,
                        description="Viewed content approval queue list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "content_type": content_type,
                            "status": status,
                            "submitted_by": submitted_by,
                            "reviewer_id": reviewer_id,
                            "order_by": order_by,
                            "order_desc": order_desc,
                            "results_count": len(approvals),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return approvals
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách yêu cầu phê duyệt: {str(e)}")
        raise ServerException(
            detail=f"Lỗi khi lấy danh sách yêu cầu phê duyệt: {str(e)}"
        )


def count_content_approvals(
    db: Session,
    content_type: Optional[str] = None,
    status: Optional[str] = None,
    submitted_by: Optional[int] = None,
    reviewer_id: Optional[int] = None,
    admin_id: Optional[int] = None,
) -> int:
    """
    Đếm số lượng yêu cầu phê duyệt.

    Args:
        db: Database session
        content_type: Lọc theo loại nội dung
        status: Lọc theo trạng thái
        submitted_by: Lọc theo người gửi
        reviewer_id: Lọc theo người duyệt
        admin_id: ID của admin thực hiện hành động

    Returns:
        Tổng số yêu cầu phê duyệt
    """
    try:
        count = ContentApprovalRepository.count(
            db, content_type, status, submitted_by, reviewer_id
        )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="CONTENT_APPROVAL",
                        entity_id=0,
                        description="Counted content approval queue items",
                        metadata={
                            "content_type": content_type,
                            "status": status,
                            "submitted_by": submitted_by,
                            "reviewer_id": reviewer_id,
                            "count": count,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return count
    except Exception as e:
        logger.error(f"Lỗi khi đếm yêu cầu phê duyệt: {str(e)}")
        raise ServerException(detail=f"Lỗi khi đếm yêu cầu phê duyệt: {str(e)}")


@cached(ttl=1800, namespace="admin:content_approvals", tags=["content_approvals"])
def get_content_approval_by_id(
    db: Session, approval_id: int, admin_id: Optional[int] = None
) -> ContentApprovalQueue:
    """
    Lấy thông tin yêu cầu phê duyệt theo ID.

    Args:
        db: Database session
        approval_id: ID yêu cầu phê duyệt
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin yêu cầu phê duyệt

    Raises:
        NotFoundException: Nếu không tìm thấy yêu cầu phê duyệt
    """
    try:
        approval = ContentApprovalRepository.get_by_id(db, approval_id)
        if not approval:
            logger.warning(f"Không tìm thấy yêu cầu phê duyệt với ID={approval_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy yêu cầu phê duyệt với ID={approval_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="CONTENT_APPROVAL",
                        entity_id=approval_id,
                        description=f"Viewed content approval details - ID: {approval_id}",
                        metadata={
                            "approval_id": approval_id,
                            "content_type": approval.content_type,
                            "content_id": approval.content_id,
                            "status": approval.status,
                            "submitted_by": approval.submitted_by,
                            "reviewer_id": approval.reviewer_id,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return approval
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin yêu cầu phê duyệt: {str(e)}")
        raise ServerException(
            detail=f"Lỗi khi lấy thông tin yêu cầu phê duyệt: {str(e)}"
        )


@invalidate_cache(tags=["content_approvals"])
def create_content_approval(
    db: Session, approval_data: ContentApprovalCreate, admin_id: Optional[int] = None
) -> ContentApprovalQueue:
    """
    Tạo yêu cầu phê duyệt nội dung mới.

    Args:
        db: Database session
        approval_data: Dữ liệu yêu cầu phê duyệt
        admin_id: ID của admin thực hiện hành động

    Returns:
        Yêu cầu phê duyệt đã tạo

    Raises:
        ConflictException: Nếu nội dung đã có yêu cầu phê duyệt đang chờ
        ServerException: Nếu có lỗi khác
    """
    try:
        # Kiểm tra xem nội dung đã có yêu cầu phê duyệt chưa
        existing_approvals = ContentApprovalRepository.get_by_content(
            db, approval_data.content_type, approval_data.content_id
        )

        # Kiểm tra các yêu cầu đang chờ
        for approval in existing_approvals:
            if approval.status == "pending":
                logger.warning(
                    f"Nội dung {approval_data.content_type}:{approval_data.content_id} "
                    f"đã có yêu cầu phê duyệt đang chờ (ID={approval.id})"
                )
                raise ConflictException(
                    detail=f"Nội dung này đã có yêu cầu phê duyệt đang chờ (ID={approval.id})"
                )

        # Chuẩn bị dữ liệu
        approval_dict = approval_data.model_dump()
        approval_dict.update(
            {
                "status": "pending",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        )

        # Tạo yêu cầu phê duyệt
        new_approval = ContentApprovalRepository.create(db, approval_dict)

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="CONTENT_APPROVAL",
                        entity_id=new_approval.id,
                        description=f"Created new content approval request - ID: {new_approval.id}",
                        metadata={
                            "approval_id": new_approval.id,
                            "content_type": new_approval.content_type,
                            "content_id": new_approval.content_id,
                            "submitted_by": new_approval.submitted_by,
                            "comments": new_approval.comments,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return new_approval
    except ConflictException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo yêu cầu phê duyệt: {str(e)}")
        raise ServerException(detail=f"Không thể tạo yêu cầu phê duyệt: {str(e)}")


@invalidate_cache(tags=["content_approvals"])
def update_content_approval(
    db: Session,
    approval_id: int,
    approval_data: ContentApprovalUpdate,
    admin_id: Optional[int] = None,
) -> ContentApprovalQueue:
    """
    Cập nhật thông tin yêu cầu phê duyệt.

    Args:
        db: Database session
        approval_id: ID yêu cầu phê duyệt
        approval_data: Dữ liệu cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Yêu cầu phê duyệt đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy yêu cầu phê duyệt
        BadRequestException: Nếu yêu cầu đã được xử lý
        ServerException: Nếu có lỗi khác
    """
    try:
        # Kiểm tra yêu cầu phê duyệt tồn tại
        approval = ContentApprovalRepository.get_by_id(db, approval_id)
        if not approval:
            logger.warning(f"Không tìm thấy yêu cầu phê duyệt với ID={approval_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy yêu cầu phê duyệt với ID={approval_id}"
            )

        # Kiểm tra trạng thái yêu cầu
        if approval.status != "pending":
            logger.warning(
                f"Yêu cầu phê duyệt ID={approval_id} đã được xử lý, không thể cập nhật"
            )
            raise BadRequestException(
                detail=f"Yêu cầu phê duyệt đã được {approval.status}, không thể cập nhật"
            )

        # Lưu dữ liệu cũ để log
        old_data = {
            "content_type": approval.content_type,
            "content_id": approval.content_id,
            "comments": approval.comments,
            "additional_data": approval.additional_data,
        }

        # Chuẩn bị dữ liệu cập nhật
        update_data = approval_data.model_dump(exclude_unset=True)
        update_data["updated_at"] = datetime.now(timezone.utc)

        # Cập nhật yêu cầu
        updated_approval = ContentApprovalRepository.update(
            db, approval_id, update_data
        )
        if not updated_approval:
            raise ServerException(
                detail=f"Không thể cập nhật yêu cầu phê duyệt với ID={approval_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                # Chuẩn bị dữ liệu mới
                new_data = {
                    "content_type": updated_approval.content_type,
                    "content_id": updated_approval.content_id,
                    "comments": updated_approval.comments,
                    "additional_data": updated_approval.additional_data,
                }

                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="CONTENT_APPROVAL",
                        entity_id=approval_id,
                        description=f"Updated content approval request - ID: {approval_id}",
                        metadata={
                            "approval_id": approval_id,
                            "old_data": old_data,
                            "new_data": new_data,
                            "changes": {
                                k: new_data[k]
                                for k in new_data
                                if old_data.get(k) != new_data.get(k)
                            },
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return updated_approval
    except (NotFoundException, BadRequestException):
        raise
    except Exception as e:
        if isinstance(e, (NotFoundException, BadRequestException, ServerException)):
            raise e

        logger.error(f"Lỗi khi cập nhật yêu cầu phê duyệt: {str(e)}")
        raise ServerException(detail=f"Không thể cập nhật yêu cầu phê duyệt: {str(e)}")


@invalidate_cache(tags=["content_approvals"])
def approve_content(
    db: Session,
    approval_id: int,
    reviewer_id: int,
    notes: Optional[str] = None,
    admin_id: Optional[int] = None,
) -> ContentApprovalQueue:
    """
    Phê duyệt nội dung.

    Args:
        db: Database session
        approval_id: ID yêu cầu phê duyệt
        reviewer_id: ID người duyệt
        notes: Ghi chú phê duyệt
        admin_id: ID của admin thực hiện hành động

    Returns:
        Yêu cầu phê duyệt đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy yêu cầu phê duyệt
        BadRequestException: Nếu yêu cầu đã được xử lý
        ServerException: Nếu có lỗi khác
    """
    try:
        # Kiểm tra yêu cầu phê duyệt tồn tại trước khi phê duyệt
        approval = ContentApprovalRepository.get_by_id(db, approval_id)
        if not approval:
            raise NotFoundException(
                detail=f"Không tìm thấy yêu cầu phê duyệt với ID={approval_id}"
            )

        # Kiểm tra trạng thái yêu cầu
        if approval.status != "pending":
            raise BadRequestException(
                detail=f"Yêu cầu phê duyệt đã được {approval.status}, không thể phê duyệt lại"
            )

        # Lưu trạng thái cũ để log
        old_status = approval.status

        # Gọi repository để phê duyệt
        updated_approval = ContentApprovalRepository.approve(
            db, approval_id, reviewer_id, notes
        )
        if not updated_approval:
            raise NotFoundException(
                detail=f"Không tìm thấy yêu cầu phê duyệt với ID={approval_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="CONTENT_APPROVAL",
                        entity_id=approval_id,
                        description=f"Approved content - ID: {approval_id}",
                        metadata={
                            "approval_id": approval_id,
                            "content_type": updated_approval.content_type,
                            "content_id": updated_approval.content_id,
                            "old_status": old_status,
                            "new_status": updated_approval.status,
                            "reviewer_id": reviewer_id,
                            "reviewed_at": (
                                updated_approval.reviewed_at.isoformat()
                                if updated_approval.reviewed_at
                                else None
                            ),
                            "notes": notes,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # TODO: Thực hiện các hành động sau khi phê duyệt, ví dụ: gửi thông báo, cập nhật trạng thái nội dung

        return updated_approval
    except (NotFoundException, BadRequestException):
        raise
    except Exception as e:
        if isinstance(e, (NotFoundException, BadRequestException)):
            raise e

        logger.error(f"Lỗi khi phê duyệt nội dung: {str(e)}")
        raise ServerException(detail=f"Không thể phê duyệt nội dung: {str(e)}")


@invalidate_cache(tags=["content_approvals"])
def reject_content(
    db: Session,
    approval_id: int,
    reviewer_id: int,
    notes: Optional[str] = None,
    admin_id: Optional[int] = None,
) -> ContentApprovalQueue:
    """
    Từ chối nội dung.

    Args:
        db: Database session
        approval_id: ID yêu cầu phê duyệt
        reviewer_id: ID người duyệt
        notes: Ghi chú từ chối
        admin_id: ID của admin thực hiện hành động

    Returns:
        Yêu cầu phê duyệt đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy yêu cầu phê duyệt
        BadRequestException: Nếu yêu cầu đã được xử lý hoặc không có ghi chú
        ServerException: Nếu có lỗi khác
    """
    try:
        # Kiểm tra ghi chú bắt buộc khi từ chối
        if not notes:
            raise BadRequestException(
                detail="Bắt buộc phải có ghi chú khi từ chối nội dung"
            )

        # Kiểm tra yêu cầu phê duyệt tồn tại trước khi từ chối
        approval = ContentApprovalRepository.get_by_id(db, approval_id)
        if not approval:
            raise NotFoundException(
                detail=f"Không tìm thấy yêu cầu phê duyệt với ID={approval_id}"
            )

        # Kiểm tra trạng thái yêu cầu
        if approval.status != "pending":
            raise BadRequestException(
                detail=f"Yêu cầu phê duyệt đã được {approval.status}, không thể từ chối"
            )

        # Lưu trạng thái cũ để log
        old_status = approval.status

        # Gọi repository để từ chối
        updated_approval = ContentApprovalRepository.reject(
            db, approval_id, reviewer_id, notes
        )
        if not updated_approval:
            raise NotFoundException(
                detail=f"Không tìm thấy yêu cầu phê duyệt với ID={approval_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="CONTENT_APPROVAL",
                        entity_id=approval_id,
                        description=f"Rejected content - ID: {approval_id}",
                        metadata={
                            "approval_id": approval_id,
                            "content_type": updated_approval.content_type,
                            "content_id": updated_approval.content_id,
                            "old_status": old_status,
                            "new_status": updated_approval.status,
                            "reviewer_id": reviewer_id,
                            "reviewed_at": (
                                updated_approval.reviewed_at.isoformat()
                                if updated_approval.reviewed_at
                                else None
                            ),
                            "notes": notes,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # TODO: Thực hiện các hành động sau khi từ chối, ví dụ: gửi thông báo

        return updated_approval
    except (NotFoundException, BadRequestException):
        raise
    except Exception as e:
        if isinstance(e, (NotFoundException, BadRequestException)):
            raise e

        logger.error(f"Lỗi khi từ chối nội dung: {str(e)}")
        raise ServerException(detail=f"Không thể từ chối nội dung: {str(e)}")
