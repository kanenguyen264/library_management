from sqlalchemy.orm import Session
from sqlalchemy import func, desc, cast, Date, and_, or_
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, date, timedelta
import random  # Tạm thời dùng để tạo dữ liệu mẫu

from app.admin_site.schemas.report import (
    UserReportResponse,
    ContentReportResponse,
    FinancialReportResponse,
    SystemReportResponse,
    ActivityReportResponse,
    UserGrowthData,
    UserDemographicData,
    UserEngagementData,
    ContentCountData,
    ContentPopularityData,
    CategoryDistributionData,
    RevenueData,
    SubscriptionData,
    PerformanceMetricData,
    ErrorCountData,
    ActivityCountData,
    UserActivityData,
)
from app.logging.setup import get_logger
from app.admin_site.repositories.report_repo import ReportRepository
from app.core.exceptions import ServerException, BadRequestException, NotFoundException
from app.admin_site.models import Report
from app.admin_site.schemas.report import ReportCreate, ReportUpdate
from app.cache.decorators import cached, invalidate_cache
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

logger = get_logger(__name__)


def get_user_report(
    db: Session, start_date: date, end_date: date
) -> UserReportResponse:
    """
    Tạo báo cáo về người dùng.

    Args:
        db: Database session
        start_date: Ngày bắt đầu
        end_date: Ngày kết thúc

    Returns:
        UserReportResponse
    """
    # Kiểm tra tham số
    if start_date > end_date:
        raise BadRequestException(detail="Ngày bắt đầu phải trước ngày kết thúc")

    # Giới hạn khoảng thời gian báo cáo
    if (end_date - start_date).days > 366:
        raise BadRequestException(detail="Khoảng thời gian báo cáo tối đa là 1 năm")

    try:
        # Lấy dữ liệu báo cáo
        report_data = ReportRepository.get_user_report_data(db, start_date, end_date)

        # Tạo response
        response = UserReportResponse(
            start_date=start_date,
            end_date=end_date,
            total_users=report_data["total_users"],
            new_users=report_data["new_users"],
            active_users=report_data["active_users"],
            user_growth=report_data["user_growth"],
            retention_rate=report_data["retention_rate"],
            demographics=report_data["demographics"],
            daily_stats=report_data["daily_stats"],
        )

        return response
    except Exception as e:
        logger.error(f"Lỗi khi tạo báo cáo người dùng: {str(e)}")
        raise ServerException(detail=f"Lỗi khi tạo báo cáo người dùng: {str(e)}")


def get_content_report(
    db: Session, start_date: date, end_date: date, content_type: Optional[str] = None
) -> ContentReportResponse:
    """
    Tạo báo cáo về nội dung.

    Args:
        db: Database session
        start_date: Ngày bắt đầu
        end_date: Ngày kết thúc
        content_type: Loại nội dung

    Returns:
        ContentReportResponse
    """
    # Kiểm tra tham số
    if start_date > end_date:
        raise BadRequestException(detail="Ngày bắt đầu phải trước ngày kết thúc")

    # Giới hạn khoảng thời gian báo cáo
    if (end_date - start_date).days > 366:
        raise BadRequestException(detail="Khoảng thời gian báo cáo tối đa là 1 năm")

    try:
        # Lấy dữ liệu báo cáo
        report_data = ReportRepository.get_content_report_data(
            db, start_date, end_date, content_type
        )

        # Tạo response
        response = ContentReportResponse(
            start_date=start_date,
            end_date=end_date,
            total_content=report_data["total_content"],
            new_content=report_data["new_content"],
            views=report_data["views"],
            likes=report_data["likes"],
            comments=report_data["comments"],
            shares=report_data["shares"],
            category_stats=report_data["category_stats"],
            daily_stats=report_data["daily_stats"],
        )

        return response
    except Exception as e:
        logger.error(f"Lỗi khi tạo báo cáo nội dung: {str(e)}")
        raise ServerException(detail=f"Lỗi khi tạo báo cáo nội dung: {str(e)}")


def get_financial_report(
    db: Session, start_date: date, end_date: date
) -> FinancialReportResponse:
    """
    Tạo báo cáo tài chính.

    Args:
        db: Database session
        start_date: Ngày bắt đầu
        end_date: Ngày kết thúc

    Returns:
        FinancialReportResponse
    """
    # Kiểm tra tham số
    if start_date > end_date:
        raise BadRequestException(detail="Ngày bắt đầu phải trước ngày kết thúc")

    # Giới hạn khoảng thời gian báo cáo
    if (end_date - start_date).days > 366:
        raise BadRequestException(detail="Khoảng thời gian báo cáo tối đa là 1 năm")

    try:
        # Lấy dữ liệu báo cáo
        report_data = ReportRepository.get_financial_report_data(
            db, start_date, end_date
        )

        # Tạo response
        response = FinancialReportResponse(
            start_date=start_date,
            end_date=end_date,
            total_revenue=report_data["total_revenue"],
            transactions=report_data["transactions"],
            average_order_value=report_data["average_order_value"],
            payment_methods=report_data["payment_methods"],
            product_categories=report_data["product_categories"],
            daily_stats=report_data["daily_stats"],
        )

        return response
    except Exception as e:
        logger.error(f"Lỗi khi tạo báo cáo tài chính: {str(e)}")
        raise ServerException(detail=f"Lỗi khi tạo báo cáo tài chính: {str(e)}")


def get_system_report(
    db: Session, start_date: date, end_date: date
) -> SystemReportResponse:
    """
    Tạo báo cáo hệ thống.

    Args:
        db: Database session
        start_date: Ngày bắt đầu
        end_date: Ngày kết thúc

    Returns:
        SystemReportResponse
    """
    # Kiểm tra tham số
    if start_date > end_date:
        raise BadRequestException(detail="Ngày bắt đầu phải trước ngày kết thúc")

    # Giới hạn khoảng thời gian báo cáo
    if (end_date - start_date).days > 366:
        raise BadRequestException(detail="Khoảng thời gian báo cáo tối đa là 1 năm")

    try:
        # Lấy dữ liệu báo cáo
        report_data = ReportRepository.get_system_report_data(db, start_date, end_date)

        # Tạo response
        response = SystemReportResponse(
            start_date=start_date,
            end_date=end_date,
            uptime=report_data["uptime"],
            response_times=report_data["response_times"],
            error_rate=report_data["error_rate"],
            resource_usage=report_data["resource_usage"],
            daily_stats=report_data["daily_stats"],
        )

        return response
    except Exception as e:
        logger.error(f"Lỗi khi tạo báo cáo hệ thống: {str(e)}")
        raise ServerException(detail=f"Lỗi khi tạo báo cáo hệ thống: {str(e)}")


def get_activity_report(
    db: Session, start_date: date, end_date: date, activity_type: Optional[str] = None
) -> ActivityReportResponse:
    """
    Tạo báo cáo hoạt động.

    Args:
        db: Database session
        start_date: Ngày bắt đầu
        end_date: Ngày kết thúc
        activity_type: Loại hoạt động

    Returns:
        ActivityReportResponse

    Raises:
        BadRequestException: Nếu tham số không hợp lệ
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra tham số
    if start_date > end_date:
        raise BadRequestException(detail="Ngày bắt đầu phải trước ngày kết thúc")

    # Giới hạn khoảng thời gian báo cáo
    if (end_date - start_date).days > 366:
        raise BadRequestException(detail="Khoảng thời gian báo cáo tối đa là 1 năm")

    try:
        # Lấy dữ liệu báo cáo
        report_data = ReportRepository.get_activity_report_data(
            db, start_date, end_date, activity_type
        )

        # Tạo response
        response = ActivityReportResponse(
            start_date=start_date,
            end_date=end_date,
            total_activities=report_data["total_activities"],
            activity_breakdown=report_data["activity_breakdown"],
            user_segments=report_data["user_segments"],
            hourly_distribution=report_data["hourly_distribution"],
            daily_stats=report_data["daily_stats"],
        )

        return response
    except Exception as e:
        logger.error(f"Lỗi khi tạo báo cáo hoạt động: {str(e)}")
        raise ServerException(detail=f"Lỗi khi tạo báo cáo hoạt động: {str(e)}")


@cached(ttl=3600, namespace="admin:reports", tags=["reports"])
def get_all_reports(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    report_type: Optional[str] = None,
    status: Optional[str] = None,
    created_by: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    order_by: str = "created_at",
    order_desc: bool = True,
    admin_id: Optional[int] = None,
) -> List[Report]:
    """
    Lấy danh sách báo cáo.

    Args:
        db: Database session
        skip: Số lượng bản ghi bỏ qua
        limit: Số lượng bản ghi tối đa
        report_type: Lọc theo loại báo cáo
        status: Lọc theo trạng thái
        created_by: Lọc theo người tạo
        start_date: Lọc từ ngày
        end_date: Lọc đến ngày
        order_by: Trường sắp xếp
        order_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách báo cáo
    """
    try:
        reports = ReportRepository.get_all(
            db,
            skip,
            limit,
            report_type,
            status,
            created_by,
            start_date,
            end_date,
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
                        entity_type="REPORTS",
                        entity_id=0,
                        description="Viewed reports list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "report_type": report_type,
                            "status": status,
                            "created_by": created_by,
                            "start_date": (
                                start_date.isoformat() if start_date else None
                            ),
                            "end_date": end_date.isoformat() if end_date else None,
                            "order_by": order_by,
                            "order_desc": order_desc,
                            "results_count": len(reports),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return reports
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách báo cáo: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy danh sách báo cáo: {str(e)}")


@cached(ttl=3600, namespace="admin:reports", tags=["reports"])
def get_report_by_id(
    db: Session, report_id: int, admin_id: Optional[int] = None
) -> Report:
    """
    Lấy thông tin báo cáo theo ID.

    Args:
        db: Database session
        report_id: ID báo cáo
        admin_id: ID của admin thực hiện hành động

    Returns:
        Report object

    Raises:
        NotFoundException: Nếu không tìm thấy báo cáo
    """
    report = ReportRepository.get_by_id(db, report_id)
    if not report:
        logger.warning(f"Không tìm thấy báo cáo với ID={report_id}")
        raise NotFoundException(detail=f"Không tìm thấy báo cáo với ID={report_id}")

    # Log admin activity
    if admin_id:
        try:
            create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="VIEW",
                    entity_type="REPORT",
                    entity_id=report_id,
                    description=f"Viewed report details",
                    metadata={
                        "report_type": report.report_type,
                        "status": report.status,
                        "created_by": report.created_by,
                        "created_at": (
                            report.created_at.isoformat() if report.created_at else None
                        ),
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    return report


@invalidate_cache(tags=["reports"])
def create_report(
    db: Session, report_data: ReportCreate, admin_id: Optional[int] = None
) -> Report:
    """
    Tạo báo cáo mới.

    Args:
        db: Database session
        report_data: Thông tin báo cáo mới
        admin_id: ID của admin thực hiện hành động

    Returns:
        Report object đã tạo

    Raises:
        BadRequestException: Nếu dữ liệu không hợp lệ
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra dữ liệu
    if not report_data.report_type:
        raise BadRequestException(
            detail="Loại báo cáo không được trống", field="report_type"
        )

    # Chuẩn bị dữ liệu
    report_dict = report_data.model_dump()
    report_dict.update(
        {
            "status": (
                "pending" if not report_dict.get("status") else report_dict["status"]
            ),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    # Tạo báo cáo mới
    try:
        created_report = ReportRepository.create(db, report_dict)

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="REPORT",
                        entity_id=created_report.id,
                        description=f"Created new report",
                        metadata={
                            "report_type": created_report.report_type,
                            "status": created_report.status,
                            "content": created_report.content,
                            "entity_type": created_report.entity_type,
                            "entity_id": created_report.entity_id,
                            "created_by": created_report.created_by,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return created_report
    except Exception as e:
        logger.error(f"Lỗi khi tạo báo cáo: {str(e)}")
        raise ServerException(detail=f"Không thể tạo báo cáo: {str(e)}")


@invalidate_cache(tags=["reports"])
def update_report(
    db: Session,
    report_id: int,
    report_data: ReportUpdate,
    admin_id: Optional[int] = None,
) -> Report:
    """
    Cập nhật thông tin báo cáo.

    Args:
        db: Database session
        report_id: ID báo cáo
        report_data: Thông tin cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Report object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy báo cáo
        BadRequestException: Nếu dữ liệu không hợp lệ
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra báo cáo tồn tại
    report = ReportRepository.get_by_id(db, report_id)
    if not report:
        logger.warning(f"Không tìm thấy báo cáo với ID={report_id}")
        raise NotFoundException(detail=f"Không tìm thấy báo cáo với ID={report_id}")

    # Chuẩn bị dữ liệu cập nhật
    update_data = report_data.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc)

    # Lưu thông tin trước khi cập nhật cho việc ghi log
    previous_data = {"status": report.status, "response": report.response}

    # Cập nhật báo cáo
    try:
        updated_report = ReportRepository.update(db, report_id, update_data)
        if not updated_report:
            raise ServerException(
                detail=f"Không thể cập nhật báo cáo với ID={report_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="REPORT",
                        entity_id=report_id,
                        description=f"Updated report",
                        metadata={
                            "previous": previous_data,
                            "updated": {
                                k: v
                                for k, v in update_data.items()
                                if k != "updated_at"
                            },
                            "report_type": report.report_type,
                            "entity_type": report.entity_type,
                            "entity_id": report.entity_id,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return updated_report
    except Exception as e:
        if isinstance(e, (NotFoundException, BadRequestException, ServerException)):
            raise e

        logger.error(f"Lỗi khi cập nhật báo cáo: {str(e)}")
        raise ServerException(detail=f"Không thể cập nhật báo cáo: {str(e)}")


@invalidate_cache(tags=["reports"])
def change_report_status(
    db: Session,
    report_id: int,
    status: str,
    response: Optional[str] = None,
    admin_id: Optional[int] = None,
) -> Report:
    """
    Cập nhật trạng thái báo cáo.

    Args:
        db: Database session
        report_id: ID báo cáo
        status: Trạng thái mới
        response: Phản hồi từ admin
        admin_id: ID của admin thực hiện hành động

    Returns:
        Report object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy báo cáo
        BadRequestException: Nếu dữ liệu không hợp lệ
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra báo cáo tồn tại
    report = ReportRepository.get_by_id(db, report_id)
    if not report:
        logger.warning(f"Không tìm thấy báo cáo với ID={report_id}")
        raise NotFoundException(detail=f"Không tìm thấy báo cáo với ID={report_id}")

    # Kiểm tra trạng thái hợp lệ
    valid_statuses = ["pending", "in_progress", "resolved", "rejected"]
    if status not in valid_statuses:
        raise BadRequestException(
            detail=f"Trạng thái không hợp lệ. Các trạng thái hợp lệ: {', '.join(valid_statuses)}",
            field="status",
        )

    # Chuẩn bị dữ liệu cập nhật
    update_data = {
        "status": status,
        "updated_at": datetime.now(timezone.utc),
        "resolved_at": (
            datetime.now(timezone.utc) if status in ["resolved", "rejected"] else None
        ),
        "resolved_by": (
            admin_id if status in ["resolved", "rejected"] and admin_id else None
        ),
    }

    if response is not None:
        update_data["response"] = response

    # Lưu thông tin trước khi cập nhật cho việc ghi log
    previous_status = report.status

    # Cập nhật báo cáo
    try:
        updated_report = ReportRepository.update(db, report_id, update_data)
        if not updated_report:
            raise ServerException(
                detail=f"Không thể cập nhật trạng thái báo cáo với ID={report_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="REPORT_STATUS",
                        entity_id=report_id,
                        description=f"Changed report status from {previous_status} to {status}",
                        metadata={
                            "previous_status": previous_status,
                            "new_status": status,
                            "response": response,
                            "report_type": report.report_type,
                            "entity_type": report.entity_type,
                            "entity_id": report.entity_id,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return updated_report
    except Exception as e:
        if isinstance(e, (NotFoundException, BadRequestException, ServerException)):
            raise e

        logger.error(f"Lỗi khi cập nhật trạng thái báo cáo: {str(e)}")
        raise ServerException(detail=f"Không thể cập nhật trạng thái báo cáo: {str(e)}")


@invalidate_cache(tags=["reports"])
def delete_report(db: Session, report_id: int, admin_id: Optional[int] = None) -> bool:
    """
    Xóa báo cáo.

    Args:
        db: Database session
        report_id: ID báo cáo
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu xóa thành công

    Raises:
        NotFoundException: Nếu không tìm thấy báo cáo
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra báo cáo tồn tại
    report = ReportRepository.get_by_id(db, report_id)
    if not report:
        logger.warning(f"Không tìm thấy báo cáo với ID={report_id}")
        raise NotFoundException(detail=f"Không tìm thấy báo cáo với ID={report_id}")

    # Log admin activity before deletion
    if admin_id:
        try:
            create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="DELETE",
                    entity_type="REPORT",
                    entity_id=report_id,
                    description=f"Deleted report",
                    metadata={
                        "report_type": report.report_type,
                        "status": report.status,
                        "entity_type": report.entity_type,
                        "entity_id": report.entity_id,
                        "created_by": report.created_by,
                        "created_at": (
                            report.created_at.isoformat() if report.created_at else None
                        ),
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    # Xóa báo cáo
    try:
        success = ReportRepository.delete(db, report_id)
        if not success:
            raise ServerException(detail=f"Không thể xóa báo cáo với ID={report_id}")

        return True
    except Exception as e:
        if isinstance(e, (NotFoundException, ServerException)):
            raise e

        logger.error(f"Lỗi khi xóa báo cáo: {str(e)}")
        raise ServerException(detail=f"Không thể xóa báo cáo: {str(e)}")


@cached(ttl=3600, namespace="admin:reports:statistics", tags=["reports", "statistics"])
def get_report_statistics(
    db: Session,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    admin_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Lấy thống kê báo cáo.

    Args:
        db: Database session
        start_date: Thống kê từ ngày
        end_date: Thống kê đến ngày
        admin_id: ID của admin thực hiện hành động

    Returns:
        Dictionary chứa thông tin thống kê
    """
    # Mặc định lấy thống kê 30 ngày gần nhất
    if not end_date:
        end_date = datetime.now(timezone.utc)
    if not start_date:
        start_date = end_date - timedelta(days=30)

    try:
        # Tổng số báo cáo
        total_count = ReportRepository.count(db, None, None, None, start_date, end_date)

        # Số lượng báo cáo theo trạng thái
        statuses = ["pending", "in_progress", "resolved", "rejected"]
        status_counts = {}
        for status in statuses:
            status_counts[status] = ReportRepository.count(
                db, None, status, None, start_date, end_date
            )

        # Số lượng báo cáo theo loại
        report_types = ReportRepository.get_distinct_values(db, "report_type")
        type_counts = {}
        for report_type in report_types:
            type_counts[report_type] = ReportRepository.count(
                db, report_type, None, None, start_date, end_date
            )

        # Số lượng báo cáo theo ngày
        daily_counts = ReportRepository.count_by_day(db, start_date, end_date)

        statistics = {
            "total_count": total_count,
            "status_counts": status_counts,
            "type_counts": type_counts,
            "daily_counts": daily_counts,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        }

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="REPORT_STATISTICS",
                        entity_id=0,
                        description=f"Viewed report statistics",
                        metadata={
                            "start_date": start_date.isoformat(),
                            "end_date": end_date.isoformat(),
                            "total_count": total_count,
                            "pending_count": status_counts.get("pending", 0),
                            "in_progress_count": status_counts.get("in_progress", 0),
                            "resolved_count": status_counts.get("resolved", 0),
                            "rejected_count": status_counts.get("rejected", 0),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return statistics
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê báo cáo: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy thống kê báo cáo: {str(e)}")
