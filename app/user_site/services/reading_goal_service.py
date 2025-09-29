from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, date, timedelta

from app.user_site.repositories.reading_goal_repo import ReadingGoalRepository
from app.user_site.repositories.user_repo import UserRepository
from app.user_site.repositories.book_repo import BookRepository
from app.core.exceptions import (
    NotFoundException,
    ForbiddenException,
    BadRequestException,
)
from app.cache.decorators import cached, invalidate_cache
from app.performance.profiling.code_profiler import CodeProfiler
from app.monitoring.metrics import Metrics
from app.cache import get_cache
from app.cache.keys import CacheKeyBuilder
from app.security.input_validation.sanitizers import sanitize_html
from app.security.access_control.rbac import check_permission
from app.logs_manager.services.user_activity_log_service import UserActivityLogService
from app.core.config import get_settings

settings = get_settings()


class ReadingGoalService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.reading_goal_repo = ReadingGoalRepository(db)
        self.user_repo = UserRepository(db)
        self.book_repo = BookRepository(db)
        self.metrics = Metrics()
        self.user_log_service = UserActivityLogService()
        self.cache = get_cache()

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="reading_goals", tags=["user_goals"])
    async def create_goal(
        self,
        user_id: int,
        goal_type: str,
        target_value: float,
        period: str,
        start_date: date,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Tạo mục tiêu đọc sách mới.

        Args:
            user_id: ID người dùng
            goal_type: Loại mục tiêu (books, pages, minutes)
            target_value: Giá trị mục tiêu
            period: Khoảng thời gian mục tiêu (day, week, month, year, custom)
            start_date: Ngày bắt đầu
            end_date: Ngày kết thúc (tùy chọn, cần thiết nếu period="custom")

        Returns:
            Thông tin mục tiêu đã tạo

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
            BadRequestException: Nếu dữ liệu không hợp lệ
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Kiểm tra goal_type hợp lệ
        valid_types = ["books", "pages", "minutes"]
        if goal_type not in valid_types:
            raise BadRequestException(
                f"Loại mục tiêu không hợp lệ. Hỗ trợ: {', '.join(valid_types)}"
            )

        # Kiểm tra period hợp lệ
        valid_periods = ["day", "week", "month", "year", "custom"]
        if period not in valid_periods:
            raise BadRequestException(
                f"Khoảng thời gian không hợp lệ. Hỗ trợ: {', '.join(valid_periods)}"
            )

        # Kiểm tra target_value hợp lệ
        if target_value <= 0:
            raise BadRequestException("Giá trị mục tiêu phải lớn hơn 0")

        # Đối với các loại mục tiêu đếm số lượng, target_value phải là số nguyên
        if goal_type in ["books", "pages"] and not target_value.is_integer():
            raise BadRequestException(
                f"Giá trị mục tiêu cho '{goal_type}' phải là số nguyên"
            )

        # Kiểm tra start_date và end_date
        today = datetime.now().date()

        if start_date < today - timedelta(days=30):
            raise BadRequestException(
                "Ngày bắt đầu không thể sớm hơn 30 ngày so với hiện tại"
            )

        # Tính toán ngày kết thúc tự động dựa trên period nếu không cung cấp
        if not end_date:
            if period == "day":
                end_date = start_date
            elif period == "week":
                end_date = start_date + timedelta(days=6)  # 7 ngày
            elif period == "month":
                # Tới ngày tương ứng của tháng tiếp theo, trừ đi 1 ngày
                if start_date.month == 12:
                    end_date = date(start_date.year + 1, 1, start_date.day) - timedelta(
                        days=1
                    )
                else:
                    try:
                        end_date = date(
                            start_date.year, start_date.month + 1, start_date.day
                        ) - timedelta(days=1)
                    except ValueError:
                        # Xử lý trường hợp tháng tiếp theo không có ngày tương ứng (ví dụ: 31/1 -> 28/2)
                        if start_date.month == 12:
                            end_date = date(start_date.year + 1, 1, 1) - timedelta(
                                days=1
                            )
                        else:
                            end_date = date(
                                start_date.year, start_date.month + 2, 1
                            ) - timedelta(days=1)
            elif period == "year":
                end_date = date(
                    start_date.year + 1, start_date.month, start_date.day
                ) - timedelta(days=1)
            elif period == "custom" and not end_date:
                raise BadRequestException(
                    "Ngày kết thúc là bắt buộc đối với khoảng thời gian tùy chỉnh"
                )

        # Kiểm tra khoảng thời gian hợp lệ
        if end_date < start_date:
            raise BadRequestException("Ngày kết thúc phải sau ngày bắt đầu")

        if (end_date - start_date).days > 366:
            raise BadRequestException("Khoảng thời gian không được vượt quá 1 năm")

        # Kiểm tra xem người dùng đã có mục tiêu trùng lặp không
        existing_goals = await self.reading_goal_repo.get_overlapping_goals(
            user_id, goal_type, start_date, end_date
        )

        if existing_goals:
            raise BadRequestException(
                "Đã có mục tiêu cùng loại trong khoảng thời gian này. Vui lòng chọn khoảng thời gian khác hoặc cập nhật mục tiêu hiện có."
            )

        # Tạo mục tiêu mới
        goal_data = {
            "user_id": user_id,
            "goal_type": goal_type,
            "target_value": (
                int(target_value) if goal_type in ["books", "pages"] else target_value
            ),
            "current_value": 0,
            "period": period,
            "start_date": start_date,
            "end_date": end_date,
            "status": "active",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        goal = await self.reading_goal_repo.create(goal_data)

        # Ghi log
        await self.user_log_service.log_activity(
            self.db,
            user_id=user_id,
            activity_type="CREATE_READING_GOAL",
            resource_type="reading_goal",
            resource_id=str(goal.id),
            metadata={
                "goal_type": goal_type,
                "target_value": goal_data["target_value"],
                "period": period,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )

        # Metrics
        self.metrics.track_user_activity("create_reading_goal", "registered")

        return {
            "id": goal.id,
            "user_id": goal.user_id,
            "goal_type": goal.goal_type,
            "target_value": goal.target_value,
            "current_value": goal.current_value,
            "period": goal.period,
            "start_date": goal.start_date,
            "end_date": goal.end_date,
            "status": goal.status,
            "progress_percentage": 0,
            "created_at": goal.created_at,
            "updated_at": goal.updated_at,
        }

    @CodeProfiler.profile_time()
    @cached(ttl=3600, namespace="reading_goals", tags=["goal_details"])
    async def get_goal(self, goal_id: int) -> Dict[str, Any]:
        """Lấy thông tin mục tiêu đọc sách.

        Args:
            goal_id: ID của mục tiêu

        Returns:
            Thông tin mục tiêu

        Raises:
            NotFoundException: Nếu không tìm thấy mục tiêu
        """
        # Tạo cache key
        cache_key = CacheKeyBuilder.build_key("reading_goal", goal_id)

        # Kiểm tra cache
        cached_data = await self.cache.get(cache_key)
        if cached_data:
            return cached_data

        # Lấy mục tiêu
        goal = await self.reading_goal_repo.get_by_id(goal_id)
        if not goal:
            raise NotFoundException(f"Không tìm thấy mục tiêu với ID {goal_id}")

        # Tính tiến độ phần trăm
        progress_percentage = 0
        if goal.target_value > 0:
            progress_percentage = min(
                100, round((goal.current_value / goal.target_value) * 100, 1)
            )

        # Kiểm tra tình trạng mục tiêu
        today = datetime.now().date()
        if goal.status == "active" and goal.end_date < today:
            # Nếu đã qua hạn
            if goal.current_value >= goal.target_value:
                goal.status = "completed"
            else:
                goal.status = "expired"

            # Cập nhật trạng thái trong DB
            await self.reading_goal_repo.update(goal_id, {"status": goal.status})

        # Tính thời gian còn lại
        days_left = 0
        if goal.status == "active":
            days_left = (goal.end_date - today).days

        result = {
            "id": goal.id,
            "user_id": goal.user_id,
            "goal_type": goal.goal_type,
            "target_value": goal.target_value,
            "current_value": goal.current_value,
            "period": goal.period,
            "start_date": goal.start_date,
            "end_date": goal.end_date,
            "status": goal.status,
            "progress_percentage": progress_percentage,
            "days_left": days_left,
            "created_at": goal.created_at,
            "updated_at": goal.updated_at,
        }

        # Lưu cache
        await self.cache.set(cache_key, result, ttl=3600)

        return result

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="reading_goals", tags=["goal_details", "user_goals"])
    async def update_goal(self, goal_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Cập nhật mục tiêu đọc sách.

        Args:
            goal_id: ID của mục tiêu
            data: Dữ liệu cập nhật

        Returns:
            Thông tin mục tiêu đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy mục tiêu
            BadRequestException: Nếu dữ liệu không hợp lệ
            ForbiddenException: Nếu không có quyền cập nhật
        """
        # Lấy mục tiêu
        goal = await self.reading_goal_repo.get_by_id(goal_id)
        if not goal:
            raise NotFoundException(f"Không tìm thấy mục tiêu với ID {goal_id}")

        # Làm sạch dữ liệu
        clean_data = {}
        for key, value in data.items():
            if isinstance(value, str) and key not in ["start_date", "end_date"]:
                clean_data[key] = sanitize_html(value)
            else:
                clean_data[key] = value

        # Kiểm tra nếu mục tiêu đã hoàn thành hoặc hết hạn
        if goal.status in ["completed", "expired"] and "status" not in clean_data:
            raise BadRequestException(f"Không thể cập nhật mục tiêu đã {goal.status}")

        # Giới hạn các trường có thể cập nhật
        allowed_fields = ["target_value", "start_date", "end_date", "status"]

        # Loại bỏ các trường không được phép cập nhật
        for key in list(clean_data.keys()):
            if key not in allowed_fields:
                del clean_data[key]

        # Kiểm tra target_value hợp lệ
        if "target_value" in clean_data:
            target_value = clean_data["target_value"]
            if target_value <= 0:
                raise BadRequestException("Giá trị mục tiêu phải lớn hơn 0")

            # Đối với các loại mục tiêu đếm số lượng, target_value phải là số nguyên
            if (
                goal.goal_type in ["books", "pages"]
                and not isinstance(target_value, int)
                and not target_value.is_integer()
            ):
                clean_data["target_value"] = int(target_value)

        # Kiểm tra start_date và end_date
        start_date = clean_data.get("start_date", goal.start_date)
        end_date = clean_data.get("end_date", goal.end_date)

        if start_date and end_date and end_date < start_date:
            raise BadRequestException("Ngày kết thúc phải sau ngày bắt đầu")

        if start_date and end_date and (end_date - start_date).days > 366:
            raise BadRequestException("Khoảng thời gian không được vượt quá 1 năm")

        # Kiểm tra xem cập nhật có tạo ra xung đột với mục tiêu khác không
        if "start_date" in clean_data or "end_date" in clean_data:
            existing_goals = await self.reading_goal_repo.get_overlapping_goals(
                goal.user_id, goal.goal_type, start_date, end_date, exclude_id=goal_id
            )

            if existing_goals:
                raise BadRequestException(
                    "Khoảng thời gian mới xung đột với mục tiêu hiện có. Vui lòng chọn khoảng thời gian khác."
                )

        # Lưu trạng thái cũ
        before_state = {
            "id": goal.id,
            "target_value": goal.target_value,
            "current_value": goal.current_value,
            "start_date": goal.start_date.isoformat(),
            "end_date": goal.end_date.isoformat(),
            "status": goal.status,
        }

        # Cập nhật mục tiêu
        updated = await self.reading_goal_repo.update(goal_id, clean_data)

        # Tính tiến độ phần trăm
        progress_percentage = 0
        if updated.target_value > 0:
            progress_percentage = min(
                100, round((updated.current_value / updated.target_value) * 100, 1)
            )

        # Ghi log
        await self.user_log_service.log_activity(
            self.db,
            user_id=goal.user_id,
            activity_type="UPDATE_READING_GOAL",
            resource_type="reading_goal",
            resource_id=str(goal_id),
            before_state=before_state,
            after_state={
                "id": updated.id,
                "target_value": updated.target_value,
                "current_value": updated.current_value,
                "start_date": updated.start_date.isoformat(),
                "end_date": updated.end_date.isoformat(),
                "status": updated.status,
            },
            metadata={"updated_fields": list(clean_data.keys())},
        )

        # Metrics
        self.metrics.track_user_activity("update_reading_goal", "registered")

        # Xóa cache
        cache_key = CacheKeyBuilder.build_key("reading_goal", goal_id)
        await self.cache.delete(cache_key)

        return {
            "id": updated.id,
            "user_id": updated.user_id,
            "goal_type": updated.goal_type,
            "target_value": updated.target_value,
            "current_value": updated.current_value,
            "period": updated.period,
            "start_date": updated.start_date,
            "end_date": updated.end_date,
            "status": updated.status,
            "progress_percentage": progress_percentage,
            "created_at": updated.created_at,
            "updated_at": updated.updated_at,
        }

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="reading_goals", tags=["goal_details", "user_goals"])
    async def delete_goal(self, goal_id: int) -> Dict[str, Any]:
        """Xóa mục tiêu đọc sách.

        Args:
            goal_id: ID của mục tiêu

        Returns:
            Thông báo kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy mục tiêu
        """
        # Lấy mục tiêu
        goal = await self.reading_goal_repo.get_by_id(goal_id)
        if not goal:
            raise NotFoundException(f"Không tìm thấy mục tiêu với ID {goal_id}")

        # Lưu thông tin trước khi xóa
        before_state = {
            "id": goal.id,
            "user_id": goal.user_id,
            "goal_type": goal.goal_type,
            "target_value": goal.target_value,
            "current_value": goal.current_value,
            "period": goal.period,
            "start_date": goal.start_date.isoformat(),
            "end_date": goal.end_date.isoformat(),
            "status": goal.status,
        }

        # Xóa mục tiêu
        await self.reading_goal_repo.delete(goal_id)

        # Ghi log
        await self.user_log_service.log_activity(
            self.db,
            user_id=goal.user_id,
            activity_type="DELETE_READING_GOAL",
            resource_type="reading_goal",
            resource_id=str(goal_id),
            before_state=before_state,
        )

        # Metrics
        self.metrics.track_user_activity("delete_reading_goal", "registered")

        # Xóa cache
        cache_key = CacheKeyBuilder.build_key("reading_goal", goal_id)
        await self.cache.delete(cache_key)

        return {"message": "Đã xóa mục tiêu thành công"}

    @CodeProfiler.profile_time()
    @cached(ttl=1800, namespace="reading_goals", tags=["user_goals"])
    async def list_user_goals(
        self, user_id: int, active_only: bool = False, skip: int = 0, limit: int = 20
    ) -> Dict[str, Any]:
        """Lấy danh sách mục tiêu của người dùng.

        Args:
            user_id: ID của người dùng
            active_only: Chỉ lấy mục tiêu đang hoạt động
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách mục tiêu và thông tin phân trang

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Tạo cache key
        cache_key = CacheKeyBuilder.build_key(
            "user_goals", user_id, active_only, skip, limit
        )

        # Kiểm tra cache
        cached_data = await self.cache.get(cache_key)
        if cached_data:
            return cached_data

        # Lấy danh sách mục tiêu
        goals = await self.reading_goal_repo.list_by_user(
            user_id, active_only, skip, limit
        )
        total = await self.reading_goal_repo.count_by_user(user_id, active_only)

        # Xử lý kết quả
        items = []
        today = datetime.now().date()

        for goal in goals:
            # Tính tiến độ phần trăm
            progress_percentage = 0
            if goal.target_value > 0:
                progress_percentage = min(
                    100, round((goal.current_value / goal.target_value) * 100, 1)
                )

            # Kiểm tra trạng thái
            status = goal.status
            if status == "active" and goal.end_date < today:
                if goal.current_value >= goal.target_value:
                    status = "completed"
                else:
                    status = "expired"

                # Cập nhật trạng thái trong DB
                await self.reading_goal_repo.update(goal.id, {"status": status})

            # Tính thời gian còn lại
            days_left = 0
            if status == "active":
                days_left = (goal.end_date - today).days

            items.append(
                {
                    "id": goal.id,
                    "user_id": goal.user_id,
                    "goal_type": goal.goal_type,
                    "target_value": goal.target_value,
                    "current_value": goal.current_value,
                    "period": goal.period,
                    "start_date": goal.start_date,
                    "end_date": goal.end_date,
                    "status": status,
                    "progress_percentage": progress_percentage,
                    "days_left": days_left,
                    "created_at": goal.created_at,
                    "updated_at": goal.updated_at,
                }
            )

        result = {"items": items, "total": total, "skip": skip, "limit": limit}

        # Lưu cache
        await self.cache.set(cache_key, result, ttl=1800)

        return result

    @CodeProfiler.profile_time()
    @cached(ttl=1800, namespace="reading_goals", tags=["active_goals"])
    async def get_active_goals(self, user_id: int) -> List[Dict[str, Any]]:
        """Lấy danh sách mục tiêu đang hoạt động của người dùng.

        Args:
            user_id: ID của người dùng

        Returns:
            Danh sách mục tiêu đang hoạt động

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Tạo cache key
        cache_key = CacheKeyBuilder.build_key("active_goals", user_id)

        # Kiểm tra cache
        cached_data = await self.cache.get(cache_key)
        if cached_data:
            return cached_data

        # Lấy danh sách mục tiêu đang hoạt động
        goals = await self.reading_goal_repo.list_by_user(user_id, active_only=True)

        # Xử lý kết quả
        active_goals = []
        today = datetime.now().date()

        for goal in goals:
            # Tính tiến độ phần trăm
            progress_percentage = 0
            if goal.target_value > 0:
                progress_percentage = min(
                    100, round((goal.current_value / goal.target_value) * 100, 1)
                )

            # Kiểm tra xem mục tiêu có thực sự còn hoạt động không
            if goal.end_date < today:
                if goal.current_value >= goal.target_value:
                    await self.reading_goal_repo.update(
                        goal.id, {"status": "completed"}
                    )
                else:
                    await self.reading_goal_repo.update(goal.id, {"status": "expired"})
                continue

            # Tính thời gian còn lại
            days_left = (goal.end_date - today).days

            # Thêm thông tin hiển thị thân thiện
            goal_type_display = {
                "books": "cuốn sách",
                "pages": "trang",
                "minutes": "phút",
            }.get(goal.goal_type, goal.goal_type)

            active_goals.append(
                {
                    "id": goal.id,
                    "goal_type": goal.goal_type,
                    "goal_type_display": goal_type_display,
                    "target_value": goal.target_value,
                    "current_value": goal.current_value,
                    "period": goal.period,
                    "start_date": goal.start_date,
                    "end_date": goal.end_date,
                    "progress_percentage": progress_percentage,
                    "days_left": days_left,
                    "remaining_value": max(0, goal.target_value - goal.current_value),
                }
            )

        # Lưu cache
        await self.cache.set(cache_key, active_goals, ttl=1800)

        return active_goals

    @CodeProfiler.profile_time()
    @invalidate_cache(
        namespace="reading_goals",
        tags=["goal_details", "user_goals", "active_goals", "goal_progress"],
    )
    async def update_goal_progress(
        self, goal_id: int, increment_value: float
    ) -> Dict[str, Any]:
        """Cập nhật tiến độ mục tiêu.

        Args:
            goal_id: ID của mục tiêu
            increment_value: Giá trị tăng thêm

        Returns:
            Thông tin mục tiêu đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy mục tiêu
            BadRequestException: Nếu dữ liệu không hợp lệ
        """
        # Lấy mục tiêu
        goal = await self.reading_goal_repo.get_by_id(goal_id)
        if not goal:
            raise NotFoundException(f"Không tìm thấy mục tiêu với ID {goal_id}")

        # Kiểm tra mục tiêu có đang hoạt động không
        if goal.status != "active":
            raise BadRequestException(f"Không thể cập nhật mục tiêu đã {goal.status}")

        # Kiểm tra giá trị tăng
        if increment_value <= 0:
            raise BadRequestException("Giá trị tăng thêm phải lớn hơn 0")

        # Đối với mục tiêu đếm số lượng, increment_value phải là số nguyên
        if (
            goal.goal_type in ["books", "pages"]
            and not isinstance(increment_value, int)
            and not increment_value.is_integer()
        ):
            increment_value = int(increment_value)

        # Lưu trạng thái cũ
        before_value = goal.current_value

        # Cập nhật tiến độ
        new_value = goal.current_value + increment_value
        updated = await self.reading_goal_repo.update(
            goal_id, {"current_value": new_value}
        )

        # Kiểm tra xem mục tiêu đã hoàn thành chưa
        if new_value >= goal.target_value:
            updated = await self.reading_goal_repo.update(
                goal_id, {"status": "completed"}
            )

            # Thông báo cho người dùng
            try:
                from app.user_site.services.notification_service import (
                    NotificationService,
                )

                notification_service = NotificationService(self.db)

                goal_type_display = {
                    "books": "cuốn sách",
                    "pages": "trang",
                    "minutes": "phút đọc",
                }.get(goal.goal_type, goal.goal_type)

                await notification_service.create_notification(
                    user_id=goal.user_id,
                    type="GOAL_COMPLETED",
                    title="Mục tiêu đọc sách đã hoàn thành!",
                    message=f"Chúc mừng! Bạn đã hoàn thành mục tiêu đọc {goal.target_value} {goal_type_display}.",
                    link="/reading-goals",
                )
            except ImportError:
                # Notification service không có sẵn
                pass

        # Tính tiến độ phần trăm
        progress_percentage = 0
        if goal.target_value > 0:
            progress_percentage = min(
                100, round((new_value / goal.target_value) * 100, 1)
            )

        # Ghi log
        await self.user_log_service.log_activity(
            self.db,
            user_id=goal.user_id,
            activity_type="UPDATE_GOAL_PROGRESS",
            resource_type="reading_goal",
            resource_id=str(goal_id),
            metadata={
                "goal_type": goal.goal_type,
                "before_value": before_value,
                "increment_value": increment_value,
                "current_value": new_value,
                "target_value": goal.target_value,
                "progress_percentage": progress_percentage,
            },
        )

        # Metrics
        self.metrics.track_user_activity("update_goal_progress", "registered")

        # Xóa cache
        cache_key = CacheKeyBuilder.build_key("reading_goal", goal_id)
        await self.cache.delete(cache_key)

        return {
            "id": updated.id,
            "goal_type": updated.goal_type,
            "target_value": updated.target_value,
            "current_value": updated.current_value,
            "status": updated.status,
            "progress_percentage": progress_percentage,
            "is_completed": updated.status == "completed",
        }

    @CodeProfiler.profile_time()
    @cached(ttl=1800, namespace="reading_goals", tags=["goal_progress"])
    async def get_goal_progress(self, goal_id: int) -> Dict[str, Any]:
        """Lấy tiến độ mục tiêu.

        Args:
            goal_id: ID của mục tiêu

        Returns:
            Thông tin tiến độ mục tiêu

        Raises:
            NotFoundException: Nếu không tìm thấy mục tiêu
        """
        # Lấy mục tiêu
        goal = await self.reading_goal_repo.get_by_id(goal_id)
        if not goal:
            raise NotFoundException(f"Không tìm thấy mục tiêu với ID {goal_id}")

        # Tính tiến độ phần trăm
        progress_percentage = 0
        if goal.target_value > 0:
            progress_percentage = min(
                100, round((goal.current_value / goal.target_value) * 100, 1)
            )

        # Kiểm tra trạng thái
        today = datetime.now().date()
        status = goal.status

        if status == "active" and goal.end_date < today:
            if goal.current_value >= goal.target_value:
                status = "completed"
            else:
                status = "expired"

            # Cập nhật trạng thái trong DB
            await self.reading_goal_repo.update(goal.id, {"status": status})

        # Tính thời gian còn lại
        days_left = 0
        if status == "active":
            days_left = (goal.end_date - today).days

        # Tính giá trị còn lại cần đạt được
        remaining_value = max(0, goal.target_value - goal.current_value)

        # Tính giá trị cần đạt mỗi ngày để hoàn thành mục tiêu
        daily_target = 0
        if status == "active" and days_left > 0:
            daily_target = remaining_value / days_left

        return {
            "id": goal.id,
            "goal_type": goal.goal_type,
            "target_value": goal.target_value,
            "current_value": goal.current_value,
            "status": status,
            "progress_percentage": progress_percentage,
            "remaining_value": remaining_value,
            "days_left": days_left,
            "daily_target": daily_target,
            "start_date": goal.start_date,
            "end_date": goal.end_date,
        }

    @CodeProfiler.profile_time()
    async def track_book_completion(self, user_id: int, book_id: int) -> Dict[str, Any]:
        """Cập nhật tiến độ mục tiêu khi hoàn thành một cuốn sách.

        Args:
            user_id: ID của người dùng
            book_id: ID của sách

        Returns:
            Thông tin cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy sách
        """
        # Kiểm tra book tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(f"Không tìm thấy sách với ID {book_id}")

        # Lấy các mục tiêu đang hoạt động
        active_goals = await self.reading_goal_repo.get_active_goals_by_type(
            user_id, "books"
        )

        # Lấy số trang của sách
        pages_count = book.page_count or 0

        # Cập nhật tất cả mục tiêu đọc sách
        updated_goals = []

        for goal in active_goals:
            # Cập nhật tiến độ
            result = await self.update_goal_progress(goal.id, 1)
            updated_goals.append(result)

        # Cập nhật mục tiêu đọc trang nếu có
        if pages_count > 0:
            page_goals = await self.reading_goal_repo.get_active_goals_by_type(
                user_id, "pages"
            )

            for goal in page_goals:
                result = await self.update_goal_progress(goal.id, pages_count)
                updated_goals.append(result)

        # Metrics
        self.metrics.track_user_activity("complete_book", "registered")

        return {
            "message": "Đã cập nhật tiến độ mục tiêu",
            "updated_goals": updated_goals,
        }

    @CodeProfiler.profile_time()
    async def track_pages_read(self, user_id: int, pages: int) -> None:
        """Cập nhật tiến độ mục tiêu khi đọc một số trang sách.

        Args:
            user_id: ID của người dùng
            pages: Số trang đã đọc
        """
        if pages <= 0:
            return

        # Lấy các mục tiêu đang hoạt động liên quan đến số trang
        active_goals = await self.reading_goal_repo.get_active_goals_by_type(
            user_id, "pages"
        )

        # Cập nhật tất cả mục tiêu
        for goal in active_goals:
            try:
                await self.update_goal_progress(goal.id, pages)
            except Exception:
                # Bỏ qua lỗi để đảm bảo việc đọc không bị gián đoạn
                pass

    @CodeProfiler.profile_time()
    async def track_reading_time(self, user_id: int, minutes: int) -> None:
        """Cập nhật tiến độ mục tiêu khi đọc trong một khoảng thời gian.

        Args:
            user_id: ID của người dùng
            minutes: Số phút đã đọc
        """
        if minutes <= 0:
            return

        # Lấy các mục tiêu đang hoạt động liên quan đến thời gian đọc
        active_goals = await self.reading_goal_repo.get_active_goals_by_type(
            user_id, "minutes"
        )

        # Cập nhật tất cả mục tiêu
        for goal in active_goals:
            try:
                await self.update_goal_progress(goal.id, minutes)
            except Exception:
                # Bỏ qua lỗi để đảm bảo việc đọc không bị gián đoạn
                pass
