from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import logging

from app.user_site.models.reading_goal import ReadingGoal, GoalType, GoalStatus
from app.user_site.repositories.reading_goal_repo import ReadingGoalRepository
from app.user_site.repositories.user_repo import UserRepository
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    BadRequestException,
)
from app.cache.decorators import cached
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

# Logger cho reading goal service
logger = logging.getLogger(__name__)


async def get_all_reading_goals(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None,
    goal_type: Optional[GoalType] = None,
    status: Optional[GoalStatus] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    sort_by: str = "created_at",
    sort_desc: bool = True,
    admin_id: Optional[int] = None,
) -> List[ReadingGoal]:
    """
    Lấy danh sách mục tiêu đọc sách với bộ lọc.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        user_id: Lọc theo ID người dùng
        goal_type: Lọc theo loại mục tiêu
        status: Lọc theo trạng thái
        from_date: Lọc từ ngày
        to_date: Lọc đến ngày
        sort_by: Sắp xếp theo trường
        sort_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách mục tiêu đọc sách
    """
    try:
        repo = ReadingGoalRepository(db)
        goals = await repo.list_goals(
            skip=skip,
            limit=limit,
            user_id=user_id,
            goal_type=goal_type,
            status=status,
            from_date=from_date,
            to_date=to_date,
            sort_by=sort_by,
            sort_desc=sort_desc,
        )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="READING_GOALS",
                        entity_id=0,
                        description="Viewed reading goals list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "user_id": user_id,
                            "goal_type": goal_type.value if goal_type else None,
                            "status": status.value if status else None,
                            "from_date": from_date.isoformat() if from_date else None,
                            "to_date": to_date.isoformat() if to_date else None,
                            "sort_by": sort_by,
                            "sort_desc": sort_desc,
                            "results_count": len(goals),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return goals
    except Exception as e:
        logger.error(f"Error retrieving reading goals: {str(e)}")
        raise


async def count_reading_goals(
    db: Session,
    user_id: Optional[int] = None,
    goal_type: Optional[GoalType] = None,
    status: Optional[GoalStatus] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> int:
    """
    Đếm số lượng mục tiêu đọc sách.

    Args:
        db: Database session
        user_id: Lọc theo ID người dùng
        goal_type: Lọc theo loại mục tiêu
        status: Lọc theo trạng thái
        from_date: Lọc từ ngày
        to_date: Lọc đến ngày

    Returns:
        Số lượng mục tiêu đọc sách
    """
    try:
        repo = ReadingGoalRepository(db)
        return await repo.count_goals(
            user_id=user_id,
            goal_type=goal_type,
            status=status,
            from_date=from_date,
            to_date=to_date,
        )
    except Exception as e:
        logger.error(f"Error counting reading goals: {str(e)}")
        raise


@cached(key_prefix="admin_reading_goal", ttl=300)
async def get_reading_goal_by_id(
    db: Session, goal_id: int, admin_id: Optional[int] = None
) -> ReadingGoal:
    """
    Lấy thông tin mục tiêu đọc sách theo ID.

    Args:
        db: Database session
        goal_id: ID của mục tiêu
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin mục tiêu đọc sách

    Raises:
        NotFoundException: Nếu không tìm thấy mục tiêu
    """
    try:
        repo = ReadingGoalRepository(db)
        goal = await repo.get_by_id(goal_id)

        if not goal:
            logger.warning(f"Reading goal with ID {goal_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy mục tiêu đọc sách với ID {goal_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="READING_GOAL",
                        entity_id=goal_id,
                        description=f"Viewed reading goal details for user {goal.user_id}",
                        metadata={
                            "user_id": goal.user_id,
                            "goal_type": (
                                goal.goal_type.value
                                if hasattr(goal, "goal_type")
                                else None
                            ),
                            "status": (
                                goal.status.value if hasattr(goal, "status") else None
                            ),
                            "target_value": goal.target_value,
                            "current_value": goal.current_value,
                            "start_date": (
                                goal.start_date.isoformat()
                                if hasattr(goal, "start_date")
                                else None
                            ),
                            "end_date": (
                                goal.end_date.isoformat()
                                if hasattr(goal, "end_date")
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return goal
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving reading goal: {str(e)}")
        raise


async def get_user_active_goals(
    db: Session, user_id: int, admin_id: Optional[int] = None
) -> List[ReadingGoal]:
    """
    Lấy danh sách mục tiêu đang hoạt động của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách mục tiêu đọc sách đang hoạt động
    """
    try:
        # Check if user exists
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        repo = ReadingGoalRepository(db)
        goals = await repo.get_user_active_goals(user_id)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="USER_ACTIVE_GOALS",
                        entity_id=user_id,
                        description=f"Viewed active reading goals for user {user_id}",
                        metadata={
                            "user_id": user_id,
                            "username": (
                                user.username if hasattr(user, "username") else None
                            ),
                            "active_goals_count": len(goals),
                            "goal_ids": [goal.id for goal in goals],
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return goals
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user active goals: {str(e)}")
        raise


async def create_reading_goal(
    db: Session, goal_data: Dict[str, Any], admin_id: Optional[int] = None
) -> ReadingGoal:
    """
    Tạo mục tiêu đọc sách mới.

    Args:
        db: Database session
        goal_data: Dữ liệu mục tiêu
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin mục tiêu đọc sách đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
        ConflictException: Nếu người dùng đã có mục tiêu tương tự
        BadRequestException: Nếu dữ liệu không hợp lệ
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(goal_data["user_id"])

        if not user:
            logger.warning(f"User with ID {goal_data['user_id']} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {goal_data['user_id']}"
            )

        # Kiểm tra dữ liệu mục tiêu
        if "target_value" not in goal_data or goal_data["target_value"] <= 0:
            raise BadRequestException(detail="Giá trị mục tiêu phải lớn hơn 0")

        if "start_date" not in goal_data or "end_date" not in goal_data:
            raise BadRequestException(detail="Ngày bắt đầu và kết thúc là bắt buộc")

        if goal_data["start_date"] >= goal_data["end_date"]:
            raise BadRequestException(detail="Ngày kết thúc phải sau ngày bắt đầu")

        # Thiết lập giá trị mặc định
        if "current_value" not in goal_data:
            goal_data["current_value"] = 0

        if "status" not in goal_data:
            goal_data["status"] = GoalStatus.ACTIVE

        # Kiểm tra xem người dùng đã có mục tiêu tương tự không
        repo = ReadingGoalRepository(db)

        # Tạo mục tiêu mới
        goal = await repo.create(goal_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="READING_GOAL",
                        entity_id=goal.id,
                        description=f"Created reading goal for user {goal.user_id}",
                        metadata={
                            "user_id": goal.user_id,
                            "username": (
                                user.username if hasattr(user, "username") else None
                            ),
                            "goal_type": (
                                goal.goal_type.value
                                if hasattr(goal, "goal_type")
                                else None
                            ),
                            "target_value": goal.target_value,
                            "current_value": goal.current_value,
                            "start_date": (
                                goal.start_date.isoformat()
                                if hasattr(goal, "start_date")
                                else None
                            ),
                            "end_date": (
                                goal.end_date.isoformat()
                                if hasattr(goal, "end_date")
                                else None
                            ),
                            "status": (
                                goal.status.value if hasattr(goal, "status") else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(
            f"Created new reading goal with ID {goal.id} for user {goal.user_id}"
        )
        return goal
    except NotFoundException:
        raise
    except ConflictException:
        raise
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Error creating reading goal: {str(e)}")
        raise


async def update_reading_goal(
    db: Session, goal_id: int, goal_data: Dict[str, Any], admin_id: Optional[int] = None
) -> ReadingGoal:
    """
    Cập nhật thông tin mục tiêu đọc sách.

    Args:
        db: Database session
        goal_id: ID của mục tiêu
        goal_data: Dữ liệu cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin mục tiêu đọc sách đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy mục tiêu
        BadRequestException: Nếu dữ liệu không hợp lệ
    """
    try:
        repo = ReadingGoalRepository(db)

        # Kiểm tra mục tiêu tồn tại và lấy dữ liệu cũ
        old_goal = await get_reading_goal_by_id(db, goal_id)

        # Kiểm tra dữ liệu cập nhật
        if "target_value" in goal_data and goal_data["target_value"] <= 0:
            raise BadRequestException(detail="Giá trị mục tiêu phải lớn hơn 0")

        if "start_date" in goal_data and "end_date" in goal_data:
            if goal_data["start_date"] >= goal_data["end_date"]:
                raise BadRequestException(detail="Ngày kết thúc phải sau ngày bắt đầu")
        elif "start_date" in goal_data and goal_data["start_date"] >= old_goal.end_date:
            raise BadRequestException(detail="Ngày bắt đầu phải trước ngày kết thúc")
        elif "end_date" in goal_data and old_goal.start_date >= goal_data["end_date"]:
            raise BadRequestException(detail="Ngày kết thúc phải sau ngày bắt đầu")

        # Cập nhật trạng thái mục tiêu dựa trên giá trị hiện tại và mục tiêu
        if "current_value" in goal_data and "status" not in goal_data:
            target = old_goal.target_value
            current = goal_data["current_value"]

            if current >= target:
                goal_data["status"] = GoalStatus.COMPLETED
            elif old_goal.status == GoalStatus.COMPLETED and current < target:
                goal_data["status"] = GoalStatus.ACTIVE

        # Cập nhật mục tiêu
        updated_goal = await repo.update(goal_id, goal_data)

        # Log admin activity
        if admin_id:
            # Prepare metadata with changed fields
            metadata = {
                "user_id": updated_goal.user_id,
                "updated_fields": list(goal_data.keys()),
                "old_values": {},
                "new_values": {},
            }

            for key in goal_data.keys():
                old_value = getattr(old_goal, key)
                new_value = getattr(updated_goal, key)

                # Handle special types for logging
                if isinstance(old_value, (datetime, GoalType, GoalStatus)):
                    if isinstance(old_value, datetime):
                        metadata["old_values"][key] = old_value.isoformat()
                    else:
                        metadata["old_values"][key] = old_value.value
                else:
                    metadata["old_values"][key] = old_value

                if isinstance(new_value, (datetime, GoalType, GoalStatus)):
                    if isinstance(new_value, datetime):
                        metadata["new_values"][key] = new_value.isoformat()
                    else:
                        metadata["new_values"][key] = new_value.value
                else:
                    metadata["new_values"][key] = new_value

            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="READING_GOAL",
                        entity_id=goal_id,
                        description=f"Updated reading goal for user {updated_goal.user_id}",
                        metadata=metadata,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Updated reading goal with ID {goal_id}")
        return updated_goal
    except NotFoundException:
        raise
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Error updating reading goal: {str(e)}")
        raise


async def delete_reading_goal(
    db: Session, goal_id: int, admin_id: Optional[int] = None
) -> None:
    """
    Xóa mục tiêu đọc sách.

    Args:
        db: Database session
        goal_id: ID của mục tiêu
        admin_id: ID của admin thực hiện hành động

    Raises:
        NotFoundException: Nếu không tìm thấy mục tiêu
    """
    try:
        # Kiểm tra mục tiêu tồn tại và lấy thông tin
        goal = await get_reading_goal_by_id(db, goal_id)

        # Xóa mục tiêu
        repo = ReadingGoalRepository(db)
        await repo.delete(goal_id)

        # Log admin activity
        if admin_id:
            try:
                # Get username for logging
                user_repo = UserRepository(db)
                user = await user_repo.get_by_id(goal.user_id)
                username = user.username if user and hasattr(user, "username") else None

                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="READING_GOAL",
                        entity_id=goal_id,
                        description=f"Deleted reading goal for user {goal.user_id}",
                        metadata={
                            "user_id": goal.user_id,
                            "username": username,
                            "goal_type": (
                                goal.goal_type.value
                                if hasattr(goal, "goal_type")
                                else None
                            ),
                            "target_value": goal.target_value,
                            "current_value": goal.current_value,
                            "start_date": (
                                goal.start_date.isoformat()
                                if hasattr(goal, "start_date")
                                else None
                            ),
                            "end_date": (
                                goal.end_date.isoformat()
                                if hasattr(goal, "end_date")
                                else None
                            ),
                            "status": (
                                goal.status.value if hasattr(goal, "status") else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Deleted reading goal with ID {goal_id}")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting reading goal: {str(e)}")
        raise


async def update_goal_progress(
    db: Session, goal_id: int, value: int, admin_id: Optional[int] = None
) -> ReadingGoal:
    """
    Cập nhật tiến độ mục tiêu đọc sách.

    Args:
        db: Database session
        goal_id: ID của mục tiêu
        value: Giá trị mới
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin mục tiêu đọc sách đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy mục tiêu
        BadRequestException: Nếu giá trị không hợp lệ
    """
    try:
        # Kiểm tra mục tiêu tồn tại và lấy dữ liệu cũ
        goal = await get_reading_goal_by_id(db, goal_id)

        # Kiểm tra giá trị hợp lệ
        if value < 0:
            raise BadRequestException(detail="Giá trị tiến độ không thể âm")

        # Cập nhật tiến độ và trạng thái
        update_data = {"current_value": value}

        if value >= goal.target_value:
            update_data["status"] = GoalStatus.COMPLETED
        elif goal.status == GoalStatus.COMPLETED and value < goal.target_value:
            update_data["status"] = GoalStatus.ACTIVE

        # Cập nhật mục tiêu
        repo = ReadingGoalRepository(db)
        updated_goal = await repo.update(goal_id, update_data)

        # Log admin activity
        if admin_id:
            try:
                # Get username for logging
                user_repo = UserRepository(db)
                user = await user_repo.get_by_id(goal.user_id)
                username = user.username if user and hasattr(user, "username") else None

                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="READING_GOAL_PROGRESS",
                        entity_id=goal_id,
                        description=f"Updated reading goal progress for user {goal.user_id}",
                        metadata={
                            "user_id": goal.user_id,
                            "username": username,
                            "previous_value": goal.current_value,
                            "new_value": value,
                            "target_value": goal.target_value,
                            "previous_status": (
                                goal.status.value if hasattr(goal, "status") else None
                            ),
                            "new_status": (
                                updated_goal.status.value
                                if hasattr(updated_goal, "status")
                                else None
                            ),
                            "completion_percentage": (
                                round((value / goal.target_value) * 100, 2)
                                if goal.target_value > 0
                                else 0
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Updated progress for reading goal with ID {goal_id}")
        return updated_goal
    except NotFoundException:
        raise
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Error updating goal progress: {str(e)}")
        raise


async def check_expired_goals(db: Session, admin_id: Optional[int] = None) -> int:
    """
    Kiểm tra và cập nhật các mục tiêu đã hết hạn.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Số lượng mục tiêu đã cập nhật
    """
    try:
        repo = ReadingGoalRepository(db)
        now = datetime.now(timezone.utc).date()

        # Lấy danh sách mục tiêu đã hết hạn nhưng chưa được cập nhật
        expired_goals = await repo.list_goals(
            status=GoalStatus.ACTIVE, end_date_before=now
        )

        updated_goals = []
        count = 0

        for goal in expired_goals:
            # Cập nhật trạng thái mục tiêu
            status = (
                GoalStatus.COMPLETED
                if goal.current_value >= goal.target_value
                else GoalStatus.FAILED
            )

            updated = await repo.update(goal.id, {"status": status})

            updated_goals.append(
                {
                    "goal_id": goal.id,
                    "user_id": goal.user_id,
                    "previous_status": (
                        goal.status.value if hasattr(goal, "status") else None
                    ),
                    "new_status": status.value,
                    "current_value": goal.current_value,
                    "target_value": goal.target_value,
                }
            )

            count += 1

        # Log admin activity
        if admin_id and count > 0:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="EXPIRED_GOALS",
                        entity_id=0,
                        description=f"Updated {count} expired reading goals",
                        metadata={
                            "count": count,
                            "current_date": now.isoformat(),
                            "updated_goals": updated_goals[:10]
                            + (
                                []
                                if len(updated_goals) <= 10
                                else [
                                    {
                                        "more": f"{len(updated_goals) - 10} more goals not shown"
                                    }
                                ]
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        if count > 0:
            logger.info(f"Updated {count} expired reading goals")

        return count
    except Exception as e:
        logger.error(f"Error checking expired goals: {str(e)}")
        raise


@cached(key_prefix="admin_reading_goal_statistics", ttl=3600)
async def get_reading_goal_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê mục tiêu đọc sách.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê mục tiêu đọc sách
    """
    try:
        repo = ReadingGoalRepository(db)

        total = await repo.count_goals()
        active = await repo.count_goals(status=GoalStatus.ACTIVE)
        completed = await repo.count_goals(status=GoalStatus.COMPLETED)
        failed = await repo.count_goals(status=GoalStatus.FAILED)

        # Thống kê theo loại mục tiêu
        by_type = {}
        for goal_type in GoalType:
            count = await repo.count_goals(goal_type=goal_type)
            by_type[goal_type.value] = count

        # Thống kê theo thời gian
        now = datetime.now(timezone.utc)
        year = now.year
        month = now.month

        this_month_goals = await repo.count_goals(
            from_date=datetime(year, month, 1),
            to_date=(
                datetime(year, month + 1, 1) if month < 12 else datetime(year + 1, 1, 1)
            ),
        )

        # Tỷ lệ thành công
        success_rate = round(completed / total * 100, 2) if total > 0 else 0

        stats = {
            "total": total,
            "active": active,
            "completed": completed,
            "failed": failed,
            "by_type": by_type,
            "this_month": this_month_goals,
            "success_rate": success_rate,
        }

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="READING_GOAL_STATISTICS",
                        entity_id=0,
                        description="Viewed reading goal statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Error retrieving reading goal statistics: {str(e)}")
        raise
