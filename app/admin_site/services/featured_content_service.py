from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
import json

from app.admin_site.models import FeaturedContent
from app.admin_site.schemas.featured_content import (
    FeaturedContentCreate,
    FeaturedContentUpdate,
    FeaturedContentResponse,
)
from app.admin_site.repositories.featured_content_repo import FeaturedContentRepository
from app.cache.decorators import cached, invalidate_cache
from app.core.exceptions import (
    NotFoundException,
    ServerException,
    BadRequestException,
    ConflictException,
)
from app.logging.setup import get_logger
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

logger = get_logger(__name__)


@cached(ttl=300, namespace="admin:featured_content", tags=["featured_content"])
def get_all_featured_contents(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    content_type: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    order_by: str = "created_at",
    order_desc: bool = True,
    admin_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Lấy danh sách nội dung nổi bật.

    Args:
        db: Database session
        skip: Số lượng bản ghi bỏ qua
        limit: Số lượng bản ghi tối đa trả về
        content_type: Loại nội dung (book, author, collection...)
        status: Trạng thái (active, inactive)
        start_date: Thời gian bắt đầu
        end_date: Thời gian kết thúc
        order_by: Sắp xếp theo trường
        order_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Dictionary chứa danh sách nội dung nổi bật và tổng số bản ghi
    """
    try:
        featured_contents, total = FeaturedContentRepository.get_multi(
            db,
            skip=skip,
            limit=limit,
            content_type=content_type,
            status=status,
            start_date=start_date,
            end_date=end_date,
            order_by=order_by,
            order_desc=order_desc,
        )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="FEATURED_CONTENT",
                        entity_id=0,
                        description="Viewed featured content list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "content_type": content_type,
                            "status": status,
                            "start_date": (
                                start_date.isoformat() if start_date else None
                            ),
                            "end_date": end_date.isoformat() if end_date else None,
                            "order_by": order_by,
                            "order_desc": order_desc,
                            "results_count": len(featured_contents),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return {"items": featured_contents, "total": total}
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách nội dung nổi bật: {str(e)}")
        raise ServerException(
            detail=f"Lỗi khi lấy danh sách nội dung nổi bật: {str(e)}"
        )


def count_featured_contents(
    db: Session, content_type: Optional[str] = None, is_active: Optional[bool] = None
) -> int:
    """
    Đếm số lượng nội dung nổi bật.

    Args:
        db: Database session
        content_type: Lọc theo loại nội dung
        is_active: Lọc theo trạng thái hoạt động

    Returns:
        Tổng số nội dung nổi bật
    """
    try:
        return FeaturedContentRepository.count(db, content_type, is_active)
    except Exception as e:
        logger.error(f"Lỗi khi đếm nội dung nổi bật: {str(e)}")
        raise ServerException(detail=f"Lỗi khi đếm nội dung nổi bật: {str(e)}")


@cached(ttl=300, namespace="admin:featured_content:id", tags=["featured_content"])
def get_featured_content_by_id(
    db: Session, featured_content_id: int, admin_id: Optional[int] = None
) -> FeaturedContentResponse:
    """
    Lấy thông tin chi tiết nội dung nổi bật theo ID.

    Args:
        db: Database session
        featured_content_id: ID của nội dung nổi bật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin chi tiết nội dung nổi bật

    Raises:
        NotFoundException: Nếu không tìm thấy nội dung nổi bật
    """
    try:
        featured_content = FeaturedContentRepository.get_by_id(db, featured_content_id)
        if not featured_content:
            raise NotFoundException(
                detail=f"Không tìm thấy nội dung nổi bật với ID: {featured_content_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="FEATURED_CONTENT",
                        entity_id=featured_content_id,
                        description=f"Viewed featured content details - ID: {featured_content_id}",
                        metadata={
                            "featured_content_id": featured_content_id,
                            "content_type": featured_content.content_type,
                            "content_id": featured_content.content_id,
                            "title": featured_content.title,
                            "status": featured_content.status,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return featured_content
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin chi tiết nội dung nổi bật: {str(e)}")
        raise ServerException(
            detail=f"Lỗi khi lấy thông tin chi tiết nội dung nổi bật: {str(e)}"
        )


@invalidate_cache(namespace="admin:featured_content", tags=["featured_content"])
def create_featured_content(
    db: Session,
    featured_content_data: FeaturedContentCreate,
    admin_id: Optional[int] = None,
) -> FeaturedContentResponse:
    """
    Tạo mới nội dung nổi bật.

    Args:
        db: Database session
        featured_content_data: Dữ liệu nội dung nổi bật cần tạo
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin nội dung nổi bật đã tạo
    """
    try:
        featured_content = FeaturedContentRepository.create(
            db, obj_in=featured_content_data
        )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="FEATURED_CONTENT",
                        entity_id=featured_content.id,
                        description=f"Created new featured content - ID: {featured_content.id}",
                        metadata={
                            "featured_content_id": featured_content.id,
                            "content_type": featured_content.content_type,
                            "content_id": featured_content.content_id,
                            "title": featured_content.title,
                            "description": featured_content.description,
                            "status": featured_content.status,
                            "position": featured_content.position,
                            "start_date": (
                                featured_content.start_date.isoformat()
                                if featured_content.start_date
                                else None
                            ),
                            "end_date": (
                                featured_content.end_date.isoformat()
                                if featured_content.end_date
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return featured_content
    except Exception as e:
        logger.error(f"Lỗi khi tạo nội dung nổi bật: {str(e)}")
        raise ServerException(detail=f"Lỗi khi tạo nội dung nổi bật: {str(e)}")


@invalidate_cache(namespace="admin:featured_content", tags=["featured_content"])
def update_featured_content(
    db: Session,
    featured_content_id: int,
    featured_content_data: FeaturedContentUpdate,
    admin_id: Optional[int] = None,
) -> FeaturedContentResponse:
    """
    Cập nhật thông tin nội dung nổi bật.

    Args:
        db: Database session
        featured_content_id: ID của nội dung nổi bật
        featured_content_data: Dữ liệu cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin nội dung nổi bật đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy nội dung nổi bật
    """
    try:
        current_featured_content = FeaturedContentRepository.get_by_id(
            db, featured_content_id
        )
        if not current_featured_content:
            raise NotFoundException(
                detail=f"Không tìm thấy nội dung nổi bật với ID: {featured_content_id}"
            )

        # Lưu dữ liệu cũ để log
        old_data = {
            "content_type": current_featured_content.content_type,
            "content_id": current_featured_content.content_id,
            "title": current_featured_content.title,
            "description": current_featured_content.description,
            "status": current_featured_content.status,
            "position": current_featured_content.position,
            "start_date": (
                current_featured_content.start_date.isoformat()
                if current_featured_content.start_date
                else None
            ),
            "end_date": (
                current_featured_content.end_date.isoformat()
                if current_featured_content.end_date
                else None
            ),
        }

        # Cập nhật
        featured_content = FeaturedContentRepository.update(
            db, db_obj=current_featured_content, obj_in=featured_content_data
        )

        # Log admin activity
        if admin_id:
            try:
                # Chuẩn bị dữ liệu mới
                new_data = {
                    "content_type": featured_content.content_type,
                    "content_id": featured_content.content_id,
                    "title": featured_content.title,
                    "description": featured_content.description,
                    "status": featured_content.status,
                    "position": featured_content.position,
                    "start_date": (
                        featured_content.start_date.isoformat()
                        if featured_content.start_date
                        else None
                    ),
                    "end_date": (
                        featured_content.end_date.isoformat()
                        if featured_content.end_date
                        else None
                    ),
                }

                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="FEATURED_CONTENT",
                        entity_id=featured_content_id,
                        description=f"Updated featured content - ID: {featured_content_id}",
                        metadata={
                            "featured_content_id": featured_content_id,
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

        return featured_content
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật nội dung nổi bật: {str(e)}")
        raise ServerException(detail=f"Lỗi khi cập nhật nội dung nổi bật: {str(e)}")


@invalidate_cache(namespace="admin:featured_content", tags=["featured_content"])
def delete_featured_content(
    db: Session, featured_content_id: int, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Xóa nội dung nổi bật.

    Args:
        db: Database session
        featured_content_id: ID của nội dung nổi bật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông báo kết quả

    Raises:
        NotFoundException: Nếu không tìm thấy nội dung nổi bật
    """
    try:
        featured_content = FeaturedContentRepository.get_by_id(db, featured_content_id)
        if not featured_content:
            raise NotFoundException(
                detail=f"Không tìm thấy nội dung nổi bật với ID: {featured_content_id}"
            )

        # Lưu dữ liệu để log trước khi xóa
        log_data = {
            "content_type": featured_content.content_type,
            "content_id": featured_content.content_id,
            "title": featured_content.title,
            "description": featured_content.description,
            "status": featured_content.status,
            "position": featured_content.position,
            "start_date": (
                featured_content.start_date.isoformat()
                if featured_content.start_date
                else None
            ),
            "end_date": (
                featured_content.end_date.isoformat()
                if featured_content.end_date
                else None
            ),
        }

        FeaturedContentRepository.delete(db, id=featured_content_id)

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="FEATURED_CONTENT",
                        entity_id=featured_content_id,
                        description=f"Deleted featured content - ID: {featured_content_id}",
                        metadata={
                            "featured_content_id": featured_content_id,
                            "content_data": log_data,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return {
            "success": True,
            "message": f"Nội dung nổi bật với ID {featured_content_id} đã được xóa thành công",
        }
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa nội dung nổi bật: {str(e)}")
        raise ServerException(detail=f"Lỗi khi xóa nội dung nổi bật: {str(e)}")


@cached(ttl=3600, namespace="admin:featured_content:active", tags=["featured_content"])
def get_active_featured_contents(
    db: Session,
    content_type: Optional[str] = None,
    limit: int = 10,
    admin_id: Optional[int] = None,
) -> List[FeaturedContentResponse]:
    """
    Lấy danh sách nội dung nổi bật đang hoạt động.

    Args:
        db: Database session
        content_type: Loại nội dung (book, author, collection...)
        limit: Số lượng bản ghi tối đa trả về
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách nội dung nổi bật đang hoạt động
    """
    try:
        featured_contents = FeaturedContentRepository.get_active_featured_contents(
            db, content_type=content_type, limit=limit
        )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="FEATURED_CONTENT",
                        entity_id=0,
                        description="Viewed active featured content list",
                        metadata={
                            "content_type": content_type,
                            "limit": limit,
                            "results_count": len(featured_contents),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return featured_contents
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách nội dung nổi bật đang hoạt động: {str(e)}")
        raise ServerException(
            detail=f"Lỗi khi lấy danh sách nội dung nổi bật đang hoạt động: {str(e)}"
        )


@invalidate_cache(namespace="admin:featured_content", tags=["featured_content"])
def update_featured_content_position(
    db: Session, positions_data: List[Dict[str, Any]], admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Cập nhật vị trí hiển thị của nhiều nội dung nổi bật.

    Args:
        db: Database session
        positions_data: Danh sách ID và vị trí mới (VD: [{"id": 1, "position": 2}, {"id": 2, "position": 1}])
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông báo kết quả
    """
    try:
        position_updates = []

        for item in positions_data:
            featured_content_id = item.get("id")
            new_position = item.get("position")

            if not featured_content_id or new_position is None:
                continue

            featured_content = FeaturedContentRepository.get_by_id(
                db, featured_content_id
            )
            if not featured_content:
                continue

            old_position = featured_content.position

            # Chỉ cập nhật khi vị trí thay đổi
            if old_position != new_position:
                FeaturedContentRepository.update_position(
                    db, id=featured_content_id, position=new_position
                )
                position_updates.append(
                    {
                        "id": featured_content_id,
                        "old_position": old_position,
                        "new_position": new_position,
                    }
                )

        # Log admin activity
        if admin_id and position_updates:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="FEATURED_CONTENT",
                        entity_id=0,
                        description="Updated featured content positions",
                        metadata={
                            "position_updates": position_updates,
                            "total_updated": len(position_updates),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return {
            "success": True,
            "message": f"Đã cập nhật vị trí cho {len(position_updates)} nội dung nổi bật",
            "updated": position_updates,
        }
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật vị trí nội dung nổi bật: {str(e)}")
        raise ServerException(
            detail=f"Lỗi khi cập nhật vị trí nội dung nổi bật: {str(e)}"
        )


@invalidate_cache(namespace="admin:featured_content", tags=["featured_content"])
def bulk_update_featured_content_status(
    db: Session,
    featured_content_ids: List[int],
    status: str,
    admin_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Cập nhật trạng thái cho nhiều nội dung nổi bật.

    Args:
        db: Database session
        featured_content_ids: Danh sách ID của nội dung nổi bật
        status: Trạng thái mới (active, inactive)
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông báo kết quả
    """
    try:
        updated_ids = FeaturedContentRepository.bulk_update_status(
            db, ids=featured_content_ids, status=status
        )

        # Log admin activity
        if admin_id and updated_ids:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="FEATURED_CONTENT",
                        entity_id=0,
                        description=f"Bulk updated featured content status to '{status}'",
                        metadata={
                            "featured_content_ids": featured_content_ids,
                            "new_status": status,
                            "updated_count": len(updated_ids),
                            "updated_ids": updated_ids,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return {
            "success": True,
            "message": f"Đã cập nhật trạng thái thành '{status}' cho {len(updated_ids)} nội dung nổi bật",
            "updated_ids": updated_ids,
        }
    except Exception as e:
        logger.error(
            f"Lỗi khi cập nhật hàng loạt trạng thái nội dung nổi bật: {str(e)}"
        )
        raise ServerException(
            detail=f"Lỗi khi cập nhật hàng loạt trạng thái nội dung nổi bật: {str(e)}"
        )


@invalidate_cache(namespace="admin:featured_content", tags=["featured_content"])
def toggle_featured_content_status(
    db: Session, featured_content_id: int, admin_id: Optional[int] = None
) -> FeaturedContentResponse:
    """
    Đổi trạng thái kích hoạt của nội dung nổi bật.

    Args:
        db: Database session
        featured_content_id: ID của nội dung nổi bật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin nội dung nổi bật đã cập nhật trạng thái

    Raises:
        NotFoundException: Nếu không tìm thấy nội dung nổi bật
    """
    try:
        # Lấy thông tin nội dung nổi bật hiện tại
        featured_content = FeaturedContentRepository.get_by_id(db, featured_content_id)
        if not featured_content:
            raise NotFoundException(
                detail=f"Không tìm thấy nội dung nổi bật với ID: {featured_content_id}"
            )

        # Lưu trạng thái cũ để log
        old_status = featured_content.status

        # Đổi trạng thái (active <-> inactive)
        new_status = "inactive" if old_status == "active" else "active"

        # Cập nhật trạng thái mới
        updated_featured = FeaturedContentRepository.update(
            db, db_obj=featured_content, obj_in={"status": new_status}
        )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="FEATURED_CONTENT",
                        entity_id=featured_content_id,
                        description=f"Toggled featured content status - ID: {featured_content_id}",
                        metadata={
                            "featured_content_id": featured_content_id,
                            "content_type": featured_content.content_type,
                            "content_id": featured_content.content_id,
                            "title": featured_content.title,
                            "old_status": old_status,
                            "new_status": new_status,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return updated_featured
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi đổi trạng thái nội dung nổi bật: {str(e)}")
        raise ServerException(
            detail=f"Lỗi khi đổi trạng thái nội dung nổi bật: {str(e)}"
        )
