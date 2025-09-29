from typing import Optional, List, Dict, Any, Tuple
from datetime import date, timezone, datetime, timedelta
from sqlalchemy import select, update, delete, func, or_, and_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from app.user_site.models.reading_goal import ReadingGoal, ReadingGoalProgress
from app.user_site.models.user import User  # Để kiểm tra user_id
from app.core.exceptions import (
    NotFoundException,
    ValidationException,
    ConflictException,
)

# Định nghĩa các loại mục tiêu hợp lệ (nếu dùng Enum hoặc cần validate)
VALID_GOAL_TYPES = ["books", "pages", "minutes", "days"]


class ReadingGoalRepository:
    """Repository cho các thao tác với Mục tiêu Đọc sách (ReadingGoal) và Tiến độ (ReadingGoalProgress)."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession."""
        self.db = db

    async def _validate_user(self, user_id: int):
        """Kiểm tra sự tồn tại của người dùng."""
        user = await self.db.get(User, user_id)
        if not user:
            raise ValidationException(f"Người dùng với ID {user_id} không tồn tại.")

    async def create(self, goal_data: Dict[str, Any]) -> ReadingGoal:
        """Tạo mục tiêu đọc sách mới.

        Args:
            goal_data: Dict chứa dữ liệu mục tiêu (user_id, goal_type, target_value, start_date, end_date, ...).

        Returns:
            Đối tượng ReadingGoal đã tạo.

        Raises:
            ValidationException: Nếu thiếu trường, dữ liệu không hợp lệ, hoặc user không tồn tại.
            ConflictException: Nếu có lỗi ràng buộc.
        """
        user_id = goal_data.get("user_id")
        goal_type = goal_data.get("goal_type")
        target_value = goal_data.get("target_value")
        start_date = goal_data.get("start_date")
        end_date = goal_data.get("end_date")

        if not all([user_id, goal_type, target_value, start_date, end_date]):
            raise ValidationException(
                "Thiếu thông tin bắt buộc: user_id, goal_type, target_value, start_date, end_date."
            )

        await self._validate_user(user_id)

        if goal_type not in VALID_GOAL_TYPES:
            raise ValidationException(
                f"Loại mục tiêu không hợp lệ: {goal_type}. Các loại hợp lệ: {VALID_GOAL_TYPES}"
            )
        if not isinstance(target_value, int) or target_value <= 0:
            raise ValidationException(
                f"Giá trị mục tiêu không hợp lệ: {target_value}. Phải là số nguyên dương."
            )
        if not isinstance(start_date, date) or not isinstance(end_date, date):
            raise ValidationException("Ngày bắt đầu và kết thúc phải là kiểu date.")
        if start_date > end_date:
            raise ValidationException(
                f"Ngày bắt đầu ({start_date}) không thể sau ngày kết thúc ({end_date})."
            )

        # Lọc dữ liệu
        allowed_fields = {
            col.name
            for col in ReadingGoal.__table__.columns
            if col.name not in ["id", "created_at", "updated_at", "completed_at"]
        }
        # current_value nên bắt đầu từ 0, is_completed là False
        filtered_data = {
            k: v for k, v in goal_data.items() if k in allowed_fields and v is not None
        }
        filtered_data["current_value"] = filtered_data.get(
            "current_value", 0
        )  # Đảm bảo có giá trị ban đầu
        filtered_data["is_completed"] = False

        goal = ReadingGoal(**filtered_data)
        self.db.add(goal)
        try:
            await self.db.commit()
            await self.db.refresh(goal, attribute_names=["user"])  # Load user
            return goal
        except IntegrityError as e:
            await self.db.rollback()
            # Có thể có ràng buộc unique trên user_id + goal_type + active period?
            raise ConflictException(f"Không thể tạo mục tiêu đọc: {e}")

    async def get_by_id(
        self, goal_id: int, with_relations: List[str] = None
    ) -> Optional[ReadingGoal]:
        """Lấy mục tiêu đọc sách theo ID.

        Args:
            goal_id: ID của mục tiêu.
            with_relations: Danh sách quan hệ cần tải (vd: ['user', 'progress_records']).

        Returns:
            Đối tượng ReadingGoal hoặc None.
        """
        query = select(ReadingGoal).where(ReadingGoal.id == goal_id)

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(ReadingGoal.user))
            if "progress_records" in with_relations:
                # Sắp xếp progress records theo thời gian tạo
                options.append(
                    selectinload(ReadingGoal.progress_records).order_by(
                        ReadingGoalProgress.created_at
                    )
                )
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_active_goal(
        self,
        user_id: int,
        goal_type: Optional[str] = None,
        target_date: Optional[date] = None,  # Ngày cụ thể để kiểm tra
        with_relations: List[str] = None,
    ) -> Optional[ReadingGoal]:
        """Lấy mục tiêu đọc sách đang hoạt động của người dùng tại một ngày cụ thể.

        Args:
            user_id: ID người dùng.
            goal_type: Lọc theo loại mục tiêu (tùy chọn).
            target_date: Ngày để kiểm tra (mặc định là hôm nay).
            with_relations: Danh sách quan hệ cần tải.

        Returns:
            Đối tượng ReadingGoal đang hoạt động hoặc None.
        """
        check_date = target_date if target_date else date.today()
        query = select(ReadingGoal).where(
            ReadingGoal.user_id == user_id,
            ReadingGoal.start_date <= check_date,
            ReadingGoal.end_date >= check_date,
            ReadingGoal.is_completed == False,  # Chỉ lấy mục tiêu chưa hoàn thành
        )

        if goal_type:
            if goal_type not in VALID_GOAL_TYPES:
                raise ValidationException(f"Loại mục tiêu không hợp lệ: {goal_type}")
            query = query.where(ReadingGoal.goal_type == goal_type)

        # Ưu tiên mục tiêu tạo gần nhất nếu có nhiều mục tiêu active cùng loại
        query = query.order_by(ReadingGoal.created_at.desc())

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(ReadingGoal.user))
            if "progress_records" in with_relations:
                options.append(
                    selectinload(ReadingGoal.progress_records).order_by(
                        ReadingGoalProgress.created_at
                    )
                )
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        # Trả về cái đầu tiên (mới nhất) nếu có nhiều
        return result.scalars().first()

    async def list_by_user(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        goal_type: Optional[str] = None,
        status: Optional[str] = None,  # 'active', 'completed', 'expired'
        start_date_filter: Optional[date] = None,
        end_date_filter: Optional[date] = None,
        sort_by: str = "created_at",
        sort_desc: bool = True,
        with_relations: List[str] = None,
    ) -> List[ReadingGoal]:
        """Liệt kê mục tiêu đọc sách của người dùng với bộ lọc và sắp xếp.

        Args:
            user_id: ID người dùng.
            skip, limit: Phân trang.
            goal_type: Lọc theo loại mục tiêu.
            status: Lọc theo trạng thái ('active', 'completed', 'expired').
            start_date_filter, end_date_filter: Lọc theo khoảng thời gian mục tiêu.
            sort_by: Trường sắp xếp ('created_at', 'start_date', 'end_date', 'target_value').
            sort_desc: Sắp xếp giảm dần.
            with_relations: Danh sách quan hệ cần tải.

        Returns:
            Danh sách ReadingGoal.
        """
        query = select(ReadingGoal).where(ReadingGoal.user_id == user_id)

        if goal_type:
            if goal_type not in VALID_GOAL_TYPES:
                raise ValidationException(f"Loại mục tiêu không hợp lệ: {goal_type}")
            query = query.where(ReadingGoal.goal_type == goal_type)

        today = date.today()
        if status == "active":
            query = query.where(
                ReadingGoal.start_date <= today,
                ReadingGoal.end_date >= today,
                ReadingGoal.is_completed == False,
            )
        elif status == "completed":
            query = query.where(ReadingGoal.is_completed == True)
        elif status == "expired":
            query = query.where(
                ReadingGoal.end_date < today, ReadingGoal.is_completed == False
            )

        if start_date_filter:
            query = query.where(ReadingGoal.start_date >= start_date_filter)
        if end_date_filter:
            query = query.where(ReadingGoal.end_date <= end_date_filter)

        # Sắp xếp
        sort_column_map = {
            "start_date": ReadingGoal.start_date,
            "end_date": ReadingGoal.end_date,
            "target_value": ReadingGoal.target_value,
            "created_at": ReadingGoal.created_at,
        }
        sort_column = sort_column_map.get(sort_by, ReadingGoal.created_at)
        order = desc(sort_column) if sort_desc else asc(sort_column)
        query = query.order_by(order)

        # Phân trang
        query = query.offset(skip).limit(limit)

        # Load relations
        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(ReadingGoal.user))
            if "progress_records" in with_relations:
                options.append(
                    selectinload(ReadingGoal.progress_records).order_by(
                        ReadingGoalProgress.created_at
                    )
                )
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_by_user(
        self,
        user_id: int,
        goal_type: Optional[str] = None,
        status: Optional[str] = None,
        start_date_filter: Optional[date] = None,
        end_date_filter: Optional[date] = None,
    ) -> int:
        """Đếm số lượng mục tiêu đọc sách của người dùng với bộ lọc."""
        query = (
            select(func.count(ReadingGoal.id))
            .select_from(ReadingGoal)
            .where(ReadingGoal.user_id == user_id)
        )

        if goal_type:
            if goal_type not in VALID_GOAL_TYPES:
                raise ValidationException(f"Loại mục tiêu không hợp lệ: {goal_type}")
            query = query.where(ReadingGoal.goal_type == goal_type)

        today = date.today()
        if status == "active":
            query = query.where(
                ReadingGoal.start_date <= today,
                ReadingGoal.end_date >= today,
                ReadingGoal.is_completed == False,
            )
        elif status == "completed":
            query = query.where(ReadingGoal.is_completed == True)
        elif status == "expired":
            query = query.where(
                ReadingGoal.end_date < today, ReadingGoal.is_completed == False
            )

        if start_date_filter:
            query = query.where(ReadingGoal.start_date >= start_date_filter)
        if end_date_filter:
            query = query.where(ReadingGoal.end_date <= end_date_filter)

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def update(self, goal_id: int, data: Dict[str, Any]) -> Optional[ReadingGoal]:
        """Cập nhật thông tin mục tiêu đọc sách.
           Chỉ cho phép cập nhật một số trường như target_value, start_date, end_date
           nếu mục tiêu chưa bắt đầu hoặc logic cho phép.

        Args:
            goal_id: ID mục tiêu.
            data: Dict chứa dữ liệu cập nhật.

        Returns:
            Đối tượng ReadingGoal đã cập nhật hoặc None nếu không tìm thấy.
        """
        goal = await self.get_by_id(goal_id)
        if not goal:
            return None  # Hoặc raise NotFoundException

        # Kiểm tra xem có được phép cập nhật không (vd: không cho sửa mục tiêu đã hoàn thành)
        if goal.is_completed:
            raise ValidationException("Không thể cập nhật mục tiêu đã hoàn thành.")

        allowed_fields = {
            "target_value",
            "start_date",
            "end_date",
            "current_value",
        }  # Các trường có thể sửa đổi
        updated = False
        new_start_date = data.get("start_date", goal.start_date)
        new_end_date = data.get("end_date", goal.end_date)

        # Validate dates
        if not isinstance(new_start_date, date):
            new_start_date = goal.start_date
        if not isinstance(new_end_date, date):
            new_end_date = goal.end_date
        if new_start_date > new_end_date:
            raise ValidationException(
                f"Ngày bắt đầu ({new_start_date}) không thể sau ngày kết thúc ({new_end_date})."
            )

        for key, value in data.items():
            if key in allowed_fields and value is not None:
                if key == "target_value":
                    if not isinstance(value, int) or value <= 0:
                        raise ValidationException(
                            f"Giá trị mục tiêu không hợp lệ: {value}. Phải là số nguyên dương."
                        )
                if key == "current_value":
                    if not isinstance(value, int) or value < 0:
                        raise ValidationException(
                            f"Giá trị hiện tại không hợp lệ: {value}. Phải là số nguyên không âm."
                        )

                if getattr(goal, key) != value:
                    setattr(goal, key, value)
                    updated = True

        if updated:
            # Tính toán lại percentage nếu current_value hoặc target_value thay đổi
            if "current_value" in data or "target_value" in data:
                # Cập nhật percentage trong bản ghi progress cuối cùng nếu cần?
                pass  # Logic này phức tạp, có thể bỏ qua hoặc chỉ cập nhật ở lần add_progress tiếp theo

            try:
                await self.db.commit()
                await self.db.refresh(
                    goal, attribute_names=["user", "progress_records"]
                )
            except IntegrityError as e:
                await self.db.rollback()
                raise ConflictException(f"Không thể cập nhật mục tiêu: {e}")

        return goal

    async def delete(self, goal_id: int) -> bool:
        """Xóa mục tiêu đọc sách.
           Cân nhắc xóa các ReadingGoalProgress liên quan (cascade delete).

        Args:
            goal_id: ID mục tiêu cần xóa.

        Returns:
            True nếu xóa thành công, False nếu không tìm thấy.
        """
        # Tùy chọn: Xóa progress records trước nếu không có cascade
        # progress_delete_query = delete(ReadingGoalProgress).where(ReadingGoalProgress.goal_id == goal_id)
        # await self.db.execute(progress_delete_query)

        query = delete(ReadingGoal).where(ReadingGoal.id == goal_id)
        result = await self.db.execute(query)
        await self.db.commit()  # Commit sau khi xóa
        return result.rowcount > 0

    async def complete_goal(
        self, goal_id: int, completed_at: Optional[datetime] = None
    ) -> Optional[ReadingGoal]:
        """Đánh dấu mục tiêu đọc sách là đã hoàn thành.

        Args:
            goal_id: ID mục tiêu.
            completed_at: Thời điểm hoàn thành (mặc định là now).

        Returns:
            Đối tượng ReadingGoal đã cập nhật hoặc None nếu không tìm thấy.
        """
        goal = await self.get_by_id(goal_id)
        if not goal:
            return None

        if goal.is_completed:
            return goal  # Đã hoàn thành rồi

        goal.is_completed = True
        goal.completed_at = completed_at if completed_at else datetime.now(timezone.utc)
        # Có thể cập nhật current_value = target_value nếu muốn
        # if goal.current_value < goal.target_value:
        #     goal.current_value = goal.target_value
        try:
            await self.db.commit()
            await self.db.refresh(goal)
            return goal
        except IntegrityError as e:
            await self.db.rollback()
            raise ConflictException(f"Không thể đánh dấu hoàn thành mục tiêu: {e}")

    async def add_progress(
        self,
        goal_id: int,
        progress_value: int,
        progress_date: Optional[datetime] = None,
    ) -> Tuple[Optional[ReadingGoal], Optional[ReadingGoalProgress]]:
        """Thêm tiến độ mới cho mục tiêu đọc sách.
           Tạo bản ghi ReadingGoalProgress và cập nhật ReadingGoal.current_value.

        Args:
            goal_id: ID của mục tiêu.
            progress_value: Giá trị tiến độ hiện tại (tổng số sách/phút/...). Sẽ được ghi vào ReadingGoalProgress.
            progress_date: Thời điểm ghi nhận tiến độ (mặc định là now).

        Returns:
            Tuple[ReadingGoal | None, ReadingGoalProgress | None]: Mục tiêu đã cập nhật và bản ghi tiến độ đã tạo.
                                                                   Trả về (None, None) nếu không tìm thấy mục tiêu hoặc mục tiêu đã hoàn thành.

        Raises:
            ValidationException: Nếu progress_value không hợp lệ.
        """
        goal = await self.get_by_id(goal_id)
        if not goal:
            # raise NotFoundException(f"Không tìm thấy mục tiêu đọc sách với ID {goal_id}")
            return None, None
        if goal.is_completed:
            # raise ValidationException(f"Mục tiêu {goal_id} đã hoàn thành, không thể thêm tiến độ.")
            return goal, None  # Trả về mục tiêu hiện tại và không có progress mới

        if not isinstance(progress_value, int) or progress_value < 0:
            raise ValidationException(
                f"Giá trị tiến độ không hợp lệ: {progress_value}. Phải là số nguyên không âm."
            )

        # Tạo bản ghi tiến độ mới
        percentage = 0
        if goal.target_value > 0:
            percentage = min(
                100.0, round((progress_value / goal.target_value) * 100, 2)
            )

        progress = ReadingGoalProgress(
            goal_id=goal_id,
            current_value=progress_value,
            percentage=percentage,
            created_at=progress_date if progress_date else datetime.now(timezone.utc),
        )
        self.db.add(progress)

        # Cập nhật giá trị denormalized trên Goal
        # Chỉ cập nhật nếu giá trị mới lớn hơn giá trị cũ (đảm bảo tiến độ không giảm)
        should_update_goal = False
        if progress_value > (goal.current_value or 0):
            goal.current_value = progress_value
            should_update_goal = True

        # Kiểm tra hoàn thành
        completed_now = False
        if goal.current_value >= goal.target_value:
            if not goal.is_completed:
                goal.is_completed = True
                goal.completed_at = progress.created_at  # Dùng thời gian của progress
                should_update_goal = True
                completed_now = True

        try:
            if should_update_goal:
                await self.db.flush()  # Flush để commit cả goal và progress cùng lúc hoặc rollback cả hai
            else:
                # Chỉ commit progress nếu goal không thay đổi
                await self.db.flush([progress])

            await self.db.commit()

            # Refresh cả hai đối tượng sau khi commit thành công
            await self.db.refresh(progress)
            if should_update_goal:
                await self.db.refresh(goal)

            return goal, progress

        except IntegrityError as e:
            await self.db.rollback()
            raise ConflictException(f"Không thể thêm tiến độ: {e}")

    async def list_progress_for_goal(
        self, goal_id: int, skip: int = 0, limit: int = 100
    ) -> List[ReadingGoalProgress]:
        """Liệt kê lịch sử tiến độ của một mục tiêu.

        Args:
            goal_id: ID của mục tiêu.
            skip, limit: Phân trang.

        Returns:
            Danh sách các bản ghi ReadingGoalProgress.
        """
        query = (
            select(ReadingGoalProgress)
            .where(ReadingGoalProgress.goal_id == goal_id)
            .order_by(desc(ReadingGoalProgress.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def calculate_current_progress_info(
        self, user_id: int, goal_type: str
    ) -> Optional[Dict[str, Any]]:
        """Tính toán thông tin tiến độ cho mục tiêu đang hoạt động của người dùng.

        Args:
            user_id: ID người dùng.
            goal_type: Loại mục tiêu.

        Returns:
            Dict chứa thông tin tiến độ hoặc None nếu không có mục tiêu hoạt động.
        """
        goal = await self.get_active_goal(user_id, goal_type)
        if not goal:
            return None

        percentage = 0
        if goal.target_value > 0:
            percentage = min(
                100.0, round(((goal.current_value or 0) / goal.target_value) * 100, 2)
            )

        days_left = 0
        today = date.today()
        if goal.end_date >= today:
            days_left = (goal.end_date - today).days

        return {
            "goal_id": goal.id,
            "goal_type": goal.goal_type,
            "current_value": goal.current_value or 0,
            "target_value": goal.target_value,
            "percentage": percentage,
            "start_date": goal.start_date,
            "end_date": goal.end_date,
            "is_completed": goal.is_completed,
            "days_left": days_left,
        }

    async def check_and_update_expired_goals(
        self, user_id: Optional[int] = None
    ) -> List[ReadingGoal]:
        """Kiểm tra và cập nhật trạng thái các mục tiêu đã hết hạn nhưng chưa hoàn thành.
           Việc này có thể chạy định kỳ.

        Args:
            user_id: ID người dùng cụ thể để kiểm tra (nếu không cung cấp, kiểm tra tất cả).

        Returns:
            Danh sách các mục tiêu đã được cập nhật (đánh dấu là is_completed=True).
        """
        today = date.today()

        query = select(ReadingGoal).where(
            ReadingGoal.end_date < today, ReadingGoal.is_completed == False
        )
        if user_id:
            query = query.where(ReadingGoal.user_id == user_id)

        result = await self.db.execute(query)
        expired_goals = result.scalars().all()

        updated_goals = []
        if not expired_goals:
            return updated_goals

        for goal in expired_goals:
            goal.is_completed = True  # Đánh dấu hoàn thành (dù thành công hay không)
            goal.completed_at = datetime.now(timezone.utc)
            # Không cần set is_successful ở đây, vì trạng thái cuối cùng đã được ghi nhận
            # Client có thể tự so sánh current_value và target_value
            updated_goals.append(goal)

        try:
            await self.db.commit()
            # Không cần refresh ở đây vì chỉ cập nhật trạng thái
        except IntegrityError as e:
            await self.db.rollback()
            # Log lỗi nhưng không nên crash job định kỳ
            print(f"Error updating expired goals: {e}")  # Thay bằng logging phù hợp

        return updated_goals
