from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.user_site.repositories.payment_repo import PaymentRepository
from app.user_site.repositories.payment_method_repo import PaymentMethodRepository
from app.user_site.repositories.user_repo import UserRepository
from app.user_site.repositories.subscription_repo import SubscriptionRepository
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ForbiddenException,
)
from app.user_site.schemas.payment import PaymentStatus
from app.logs_manager.services import create_user_activity_log
from app.logs_manager.schemas.user_activity_log import UserActivityLogCreate
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


class PaymentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.payment_repo = PaymentRepository(db)
        self.payment_method_repo = PaymentMethodRepository(db)
        self.user_repo = UserRepository(db)
        self.subscription_repo = SubscriptionRepository(db)
        self.metrics = Metrics()
        self.user_log_service = UserActivityLogService()
        self.cache = get_cache()

    @CodeProfiler.profile_time(threshold=0.5)
    @invalidate_cache(namespace="payments", tags=["user_payment_methods"])
    async def create_payment_method(
        self, user_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Tạo phương thức thanh toán mới cho người dùng.

        Args:
            user_id: ID của người dùng
            data: Dữ liệu phương thức thanh toán

        Returns:
            Thông tin phương thức thanh toán đã tạo

        Raises:
            BadRequestException: Nếu thiếu thông tin hoặc dữ liệu không hợp lệ
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Kiểm tra dữ liệu
        required_fields = ["type", "provider"]
        for field in required_fields:
            if field not in data:
                raise BadRequestException(f"Thiếu trường {field}")

        # Làm sạch dữ liệu
        if "description" in data:
            data["description"] = sanitize_html(data["description"])

        # Kiểm tra loại phương thức thanh toán
        valid_types = [
            "credit_card",
            "bank_account",
            "e_wallet",
            "momo",
            "zalopay",
            "other",
        ]
        if data["type"] not in valid_types:
            raise BadRequestException(
                f"Loại phương thức thanh toán không hợp lệ. Chọn một trong: {', '.join(valid_types)}"
            )

        # Thêm user_id vào data
        data["user_id"] = user_id

        # Kiểm tra nếu là thẻ tín dụng, cần mã hóa thông tin thẻ
        if data["type"] == "credit_card" and "card_number" in data:
            # Trong thực tế, cần sử dụng dịch vụ mã hóa an toàn (PCI DSS)
            # Ở đây chỉ demo giữ 4 số cuối
            last_digits = (
                data["card_number"][-4:]
                if len(data["card_number"]) >= 4
                else data["card_number"]
            )
            data["card_number"] = f"****-****-****-{last_digits}"

        # Tạo phương thức thanh toán mới
        payment_method = await self.payment_method_repo.create(data)

        # Nếu là phương thức thanh toán đầu tiên, đặt làm mặc định
        payment_methods_count = await self.payment_method_repo.count(user_id=user_id)
        if payment_methods_count == 1:
            await self.payment_method_repo.update(
                payment_method["id"], {"is_default": True}
            )
            payment_method["is_default"] = True

        # Ghi log hoạt động
        await self.user_log_service.log_activity(
            self.db,
            user_id=user_id,
            activity_type="CREATE_PAYMENT_METHOD",
            resource_type="payment_method",
            resource_id=str(payment_method["id"]),
            metadata={"type": data["type"], "provider": data["provider"]},
        )

        # Metrics
        self.metrics.track_user_activity("add_payment_method", "registered")

        return payment_method

    @CodeProfiler.profile_time()
    @cached(ttl=3600, namespace="payments", tags=["payment_method_details"])
    async def get_payment_method(
        self, payment_method_id: int, user_id: int
    ) -> Dict[str, Any]:
        """
        Lấy thông tin phương thức thanh toán.

        Args:
            payment_method_id: ID của phương thức thanh toán
            user_id: ID của người dùng (để kiểm tra quyền)

        Returns:
            Thông tin phương thức thanh toán

        Raises:
            NotFoundException: Nếu không tìm thấy phương thức thanh toán
            ForbiddenException: Nếu phương thức thanh toán không thuộc về người dùng
        """
        # Lấy phương thức thanh toán
        payment_method = await self.payment_method_repo.get(payment_method_id)
        if not payment_method:
            raise NotFoundException(
                f"Không tìm thấy phương thức thanh toán với ID {payment_method_id}"
            )

        # Kiểm tra quyền
        if payment_method["user_id"] != user_id:
            try:
                is_admin = await check_permission(user_id, "manage_payments")
                if not is_admin:
                    raise ForbiddenException(
                        "Bạn không có quyền xem phương thức thanh toán này"
                    )
            except:
                raise ForbiddenException(
                    "Bạn không có quyền xem phương thức thanh toán này"
                )

        return payment_method

    @CodeProfiler.profile_time()
    @cached(ttl=1800, namespace="payments", tags=["user_payment_methods"])
    async def list_user_payment_methods(self, user_id: int) -> Dict[str, Any]:
        """
        Lấy danh sách phương thức thanh toán của người dùng.

        Args:
            user_id: ID của người dùng

        Returns:
            Danh sách phương thức thanh toán
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Lấy danh sách phương thức thanh toán
        payment_methods = await self.payment_method_repo.get_multi(
            user_id=user_id, sort_by="created_at", sort_desc=True
        )

        # Lấy tổng số lượng
        total = await self.payment_method_repo.count(user_id=user_id)

        return {"items": payment_methods, "total": total}

    @CodeProfiler.profile_time()
    @invalidate_cache(
        namespace="payments", tags=["payment_method_details", "user_payment_methods"]
    )
    async def update_payment_method(
        self, payment_method_id: int, user_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Cập nhật thông tin phương thức thanh toán.

        Args:
            payment_method_id: ID của phương thức thanh toán
            user_id: ID của người dùng (để kiểm tra quyền)
            data: Dữ liệu cập nhật

        Returns:
            Thông tin phương thức thanh toán đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy phương thức thanh toán
            ForbiddenException: Nếu người dùng không có quyền cập nhật
        """
        # Lấy phương thức thanh toán
        payment_method = await self.payment_method_repo.get(payment_method_id)
        if not payment_method:
            raise NotFoundException(
                f"Không tìm thấy phương thức thanh toán với ID {payment_method_id}"
            )

        # Kiểm tra quyền
        if payment_method["user_id"] != user_id:
            try:
                is_admin = await check_permission(user_id, "manage_payments")
                if not is_admin:
                    raise ForbiddenException(
                        "Bạn không có quyền cập nhật phương thức thanh toán này"
                    )
            except:
                raise ForbiddenException(
                    "Bạn không có quyền cập nhật phương thức thanh toán này"
                )

        # Lưu trạng thái cũ
        before_state = dict(payment_method)

        # Làm sạch dữ liệu
        if "description" in data:
            data["description"] = sanitize_html(data["description"])

        # Giới hạn các trường có thể cập nhật
        allowed_fields = ["description", "is_default", "expires_at", "status"]
        update_data = {k: v for k, v in data.items() if k in allowed_fields}

        # Đảm bảo không thể thay đổi loại và nhà cung cấp
        if "type" in update_data or "provider" in update_data:
            raise BadRequestException(
                "Không thể thay đổi loại hoặc nhà cung cấp của phương thức thanh toán"
            )

        # Nếu đặt làm mặc định, bỏ mặc định các phương thức khác
        if update_data.get("is_default") == True:
            await self.payment_method_repo.unset_default(user_id)

        # Cập nhật
        updated_payment_method = await self.payment_method_repo.update(
            payment_method_id, update_data
        )

        # Ghi log hoạt động
        await self.user_log_service.log_activity(
            self.db,
            user_id=user_id,
            activity_type="UPDATE_PAYMENT_METHOD",
            resource_type="payment_method",
            resource_id=str(payment_method_id),
            before_state=before_state,
            after_state=dict(updated_payment_method),
            metadata={
                "type": payment_method["type"],
                "provider": payment_method["provider"],
            },
        )

        # Metrics
        self.metrics.track_user_activity("update_payment_method", "registered")

        return updated_payment_method

    @CodeProfiler.profile_time()
    @invalidate_cache(
        namespace="payments", tags=["payment_method_details", "user_payment_methods"]
    )
    async def delete_payment_method(
        self, payment_method_id: int, user_id: int
    ) -> Dict[str, Any]:
        """
        Xóa phương thức thanh toán.

        Args:
            payment_method_id: ID của phương thức thanh toán
            user_id: ID của người dùng (để kiểm tra quyền)

        Returns:
            Thông báo kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy phương thức thanh toán
            ForbiddenException: Nếu người dùng không có quyền xóa
        """
        # Lấy phương thức thanh toán
        payment_method = await self.payment_method_repo.get(payment_method_id)
        if not payment_method:
            raise NotFoundException(
                f"Không tìm thấy phương thức thanh toán với ID {payment_method_id}"
            )

        # Kiểm tra quyền
        if payment_method["user_id"] != user_id:
            try:
                is_admin = await check_permission(user_id, "manage_payments")
                if not is_admin:
                    raise ForbiddenException(
                        "Bạn không có quyền xóa phương thức thanh toán này"
                    )
            except:
                raise ForbiddenException(
                    "Bạn không có quyền xóa phương thức thanh toán này"
                )

        # Kiểm tra xem có thanh toán đang xử lý không
        has_pending_payments = await self.payment_repo.has_pending_payments(
            payment_method_id
        )
        if has_pending_payments:
            raise BadRequestException(
                "Không thể xóa phương thức thanh toán vì đang có thanh toán đang xử lý"
            )

        # Lưu trước khi xóa để ghi log
        method_info = dict(payment_method)

        # Xóa phương thức thanh toán
        result = await self.payment_method_repo.delete(payment_method_id)

        # Nếu là phương thức mặc định, đặt phương thức khác làm mặc định
        if payment_method["is_default"]:
            other_methods = await self.payment_method_repo.get_multi(
                user_id=user_id, limit=1, sort_by="created_at", sort_desc=True
            )
            if other_methods:
                await self.payment_method_repo.update(
                    other_methods[0]["id"], {"is_default": True}
                )

        # Ghi log hoạt động
        await self.user_log_service.log_activity(
            self.db,
            user_id=user_id,
            activity_type="DELETE_PAYMENT_METHOD",
            resource_type="payment_method",
            resource_id=str(payment_method_id),
            before_state=method_info,
            metadata={"type": method_info["type"], "provider": method_info["provider"]},
        )

        # Metrics
        self.metrics.track_user_activity("delete_payment_method", "registered")

        return {
            "success": result,
            "message": "Đã xóa phương thức thanh toán thành công",
        }

    @CodeProfiler.profile_time()
    @invalidate_cache(
        namespace="payments", tags=["payment_method_details", "user_payment_methods"]
    )
    async def set_default_payment_method(
        self, payment_method_id: int, user_id: int
    ) -> Dict[str, Any]:
        """
        Đặt phương thức thanh toán mặc định.

        Args:
            payment_method_id: ID của phương thức thanh toán
            user_id: ID của người dùng (để kiểm tra quyền)

        Returns:
            Thông tin phương thức thanh toán đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy phương thức thanh toán
            ForbiddenException: Nếu người dùng không có quyền cập nhật
        """
        # Lấy phương thức thanh toán
        payment_method = await self.payment_method_repo.get(payment_method_id)
        if not payment_method:
            raise NotFoundException(
                f"Không tìm thấy phương thức thanh toán với ID {payment_method_id}"
            )

        # Kiểm tra quyền
        if payment_method["user_id"] != user_id:
            try:
                is_admin = await check_permission(user_id, "manage_payments")
                if not is_admin:
                    raise ForbiddenException(
                        "Bạn không có quyền cập nhật phương thức thanh toán này"
                    )
            except:
                raise ForbiddenException(
                    "Bạn không có quyền cập nhật phương thức thanh toán này"
                )

        # Bỏ mặc định các phương thức khác
        await self.payment_method_repo.unset_default(user_id)

        # Đặt phương thức này làm mặc định
        updated_payment_method = await self.payment_method_repo.update(
            payment_method_id, {"is_default": True}
        )

        # Ghi log hoạt động
        await self.user_log_service.log_activity(
            self.db,
            user_id=user_id,
            activity_type="SET_DEFAULT_PAYMENT_METHOD",
            resource_type="payment_method",
            resource_id=str(payment_method_id),
            metadata={
                "type": payment_method["type"],
                "provider": payment_method["provider"],
            },
        )

        # Metrics
        self.metrics.track_user_activity("set_default_payment_method", "registered")

        return updated_payment_method

    @CodeProfiler.profile_time(threshold=0.5)
    @invalidate_cache(namespace="payments", tags=["user_payments"])
    async def create_payment(
        self, user_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Tạo giao dịch thanh toán mới.

        Args:
            user_id: ID của người dùng
            data: Dữ liệu thanh toán

        Returns:
            Thông tin giao dịch thanh toán đã tạo

        Raises:
            BadRequestException: Nếu thiếu thông tin hoặc dữ liệu không hợp lệ
            NotFoundException: Nếu không tìm thấy phương thức thanh toán
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Kiểm tra dữ liệu
        required_fields = ["amount", "currency", "purpose"]
        for field in required_fields:
            if field not in data:
                raise BadRequestException(f"Thiếu trường {field}")

        # Kiểm tra số tiền
        if data["amount"] <= 0:
            raise BadRequestException("Số tiền phải lớn hơn 0")

        # Làm sạch dữ liệu
        if "description" in data:
            data["description"] = sanitize_html(data["description"])

        # Lấy phương thức thanh toán
        payment_method_id = data.get("payment_method_id")
        if payment_method_id:
            payment_method = await self.payment_method_repo.get(payment_method_id)
            if not payment_method:
                raise NotFoundException(
                    f"Không tìm thấy phương thức thanh toán với ID {payment_method_id}"
                )

            # Kiểm tra quyền sử dụng phương thức thanh toán
            if payment_method["user_id"] != user_id:
                raise ForbiddenException(
                    "Bạn không có quyền sử dụng phương thức thanh toán này"
                )
        else:
            # Lấy phương thức thanh toán mặc định
            default_methods = await self.payment_method_repo.get_multi(
                user_id=user_id, is_default=True, limit=1
            )
            if default_methods:
                payment_method = default_methods[0]
                payment_method_id = payment_method["id"]
            else:
                raise BadRequestException(
                    "Không có phương thức thanh toán mặc định, vui lòng chỉ định phương thức thanh toán"
                )

        # Thêm các thông tin cần thiết
        payment_data = {
            "user_id": user_id,
            "payment_method_id": payment_method_id,
            "amount": data["amount"],
            "currency": data["currency"],
            "purpose": data["purpose"],
            "description": data.get("description"),
            "status": "pending",
            "reference_id": self._generate_reference_id(user_id),
        }

        # Tạo thanh toán
        payment = await self.payment_repo.create(payment_data)

        # Ghi log hoạt động
        await self.user_log_service.log_activity(
            self.db,
            user_id=user_id,
            activity_type="CREATE_PAYMENT",
            resource_type="payment",
            resource_id=str(payment["id"]),
            metadata={
                "amount": data["amount"],
                "currency": data["currency"],
                "purpose": data["purpose"],
                "payment_method_id": payment_method_id,
            },
        )

        # Metrics
        self.metrics.track_user_activity("create_payment", "registered")

        # Xử lý thanh toán (async)
        try:
            # Trong thực tế, sẽ gọi một task async để xử lý thanh toán
            # Ví dụ: await background_tasks.add_task(self._process_payment, payment["id"])
            # Ở đây chỉ giả định thanh toán sẽ được xử lý sau
            pass
        except Exception as e:
            # Log lỗi nhưng không fail request
            print(f"Lỗi khi đặt lịch xử lý thanh toán: {str(e)}")

        return payment

    @CodeProfiler.profile_time()
    @cached(ttl=1800, namespace="payments", tags=["payment_details"])
    async def get_payment(self, payment_id: int, user_id: int) -> Dict[str, Any]:
        """
        Lấy thông tin giao dịch thanh toán.

        Args:
            payment_id: ID của giao dịch thanh toán
            user_id: ID của người dùng (để kiểm tra quyền)

        Returns:
            Thông tin giao dịch thanh toán

        Raises:
            NotFoundException: Nếu không tìm thấy giao dịch thanh toán
            ForbiddenException: Nếu giao dịch thanh toán không thuộc về người dùng
        """
        # Lấy thanh toán
        payment = await self.payment_repo.get(payment_id)
        if not payment:
            raise NotFoundException(f"Không tìm thấy thanh toán với ID {payment_id}")

        # Kiểm tra quyền
        if payment["user_id"] != user_id:
            try:
                is_admin = await check_permission(user_id, "manage_payments")
                if not is_admin:
                    raise ForbiddenException("Bạn không có quyền xem thanh toán này")
            except:
                raise ForbiddenException("Bạn không có quyền xem thanh toán này")

        # Lấy thông tin phương thức thanh toán
        if payment["payment_method_id"]:
            payment_method = await self.payment_method_repo.get(
                payment["payment_method_id"]
            )
            if payment_method:
                payment["payment_method"] = {
                    "id": payment_method["id"],
                    "type": payment_method["type"],
                    "provider": payment_method["provider"],
                }

        return payment

    @CodeProfiler.profile_time()
    @cached(ttl=1800, namespace="payments", tags=["user_payments"])
    async def list_user_payments(
        self, user_id: int, skip: int = 0, limit: int = 20
    ) -> Dict[str, Any]:
        """
        Lấy danh sách giao dịch thanh toán của người dùng.

        Args:
            user_id: ID của người dùng
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách giao dịch thanh toán và thông tin phân trang
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Lấy danh sách thanh toán
        payments = await self.payment_repo.get_multi(
            user_id=user_id,
            skip=skip,
            limit=limit,
            sort_by="created_at",
            sort_desc=True,
        )

        # Lấy tổng số lượng
        total = await self.payment_repo.count(user_id=user_id)

        # Lấy thông tin phương thức thanh toán cho mỗi thanh toán
        for payment in payments:
            if payment["payment_method_id"]:
                payment_method = await self.payment_method_repo.get(
                    payment["payment_method_id"]
                )
                if payment_method:
                    payment["payment_method"] = {
                        "id": payment_method["id"],
                        "type": payment_method["type"],
                        "provider": payment_method["provider"],
                    }

        return {"items": payments, "total": total, "skip": skip, "limit": limit}

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="payments", tags=["payment_details", "user_payments"])
    async def update_payment_status(
        self,
        payment_id: int,
        status: str,
        transaction_id: Optional[str] = None,
        error_message: Optional[str] = None,
        admin_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Cập nhật trạng thái giao dịch thanh toán.

        Args:
            payment_id: ID của giao dịch thanh toán
            status: Trạng thái mới (ví dụ: success, failed, refunded)
            transaction_id: Mã giao dịch (tùy chọn)
            error_message: Thông báo lỗi nếu có (tùy chọn)
            admin_id: ID của admin thực hiện hành động (tùy chọn)

        Returns:
            Thông tin giao dịch thanh toán đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy giao dịch thanh toán
        """
        # Lấy thanh toán
        payment = await self.payment_repo.get(payment_id)
        if not payment:
            raise NotFoundException(f"Không tìm thấy thanh toán với ID {payment_id}")

        # Kiểm tra quyền (chỉ admin hoặc hệ thống có thể cập nhật trạng thái)
        if admin_id:
            try:
                is_admin = await check_permission(admin_id, "manage_payments")
                if not is_admin:
                    raise ForbiddenException(
                        "Bạn không có quyền cập nhật trạng thái thanh toán"
                    )
            except:
                raise ForbiddenException(
                    "Bạn không có quyền cập nhật trạng thái thanh toán"
                )

        # Kiểm tra trạng thái hợp lệ
        valid_statuses = [
            "pending",
            "processing",
            "completed",
            "failed",
            "refunded",
            "cancelled",
        ]
        if status not in valid_statuses:
            raise BadRequestException(
                f"Trạng thái không hợp lệ. Chọn một trong: {', '.join(valid_statuses)}"
            )

        # Kiểm tra logic chuyển trạng thái
        current_status = payment["status"]
        if current_status == "completed" and status not in ["refunded", "completed"]:
            raise BadRequestException(
                "Không thể thay đổi trạng thái từ 'completed' sang trạng thái khác không phải 'refunded'"
            )

        if current_status == "refunded" and status != "refunded":
            raise BadRequestException("Không thể thay đổi trạng thái từ 'refunded'")

        # Lưu trạng thái cũ
        before_state = dict(payment)

        # Cập nhật trạng thái
        update_data = {"status": status}
        if transaction_id:
            update_data["transaction_id"] = transaction_id
        if error_message:
            update_data["error_message"] = sanitize_html(error_message)
        if status in ["completed", "failed", "refunded", "cancelled"]:
            update_data["completed_at"] = datetime.now().isoformat()

        # Cập nhật thanh toán
        updated_payment = await self.payment_repo.update(payment_id, update_data)

        # Ghi log hoạt động
        log_user_id = admin_id if admin_id else payment["user_id"]
        await self.user_log_service.log_activity(
            self.db,
            user_id=log_user_id,
            activity_type="UPDATE_PAYMENT_STATUS",
            resource_type="payment",
            resource_id=str(payment_id),
            before_state=before_state,
            after_state=dict(updated_payment),
            metadata={
                "old_status": current_status,
                "new_status": status,
                "transaction_id": transaction_id,
            },
        )

        # Metrics
        self.metrics.track_user_activity(
            "update_payment_status", "admin" if admin_id else "system"
        )

        # Gửi thông báo cho người dùng
        try:
            from app.user_site.services.notification_service import NotificationService

            notification_service = NotificationService(self.db)

            # Tạo thông báo dựa trên trạng thái
            title = f"Cập nhật thanh toán #{payment_id}"
            message = ""

            if status == "completed":
                message = f"Thanh toán {payment['amount']} {payment['currency']} cho {payment['purpose']} đã hoàn tất."
            elif status == "failed":
                message = f"Thanh toán {payment['amount']} {payment['currency']} cho {payment['purpose']} đã thất bại."
            elif status == "refunded":
                message = f"Thanh toán {payment['amount']} {payment['currency']} cho {payment['purpose']} đã được hoàn tiền."

            if message:
                await notification_service.create_notification(
                    user_id=payment["user_id"],
                    type="PAYMENT_UPDATE",
                    title=title,
                    message=message,
                    link=f"/payments/{payment_id}",
                )
        except Exception as e:
            # Log lỗi nhưng không fail request
            print(f"Lỗi khi gửi thông báo thanh toán: {str(e)}")

        return updated_payment

    @CodeProfiler.profile_time(threshold=0.5)
    async def process_payment(self, payment_id: int) -> Dict[str, Any]:
        """
        Xử lý giao dịch thanh toán.

        Args:
            payment_id: ID của giao dịch thanh toán

        Returns:
            Thông tin giao dịch thanh toán đã xử lý

        Raises:
            NotFoundException: Nếu không tìm thấy giao dịch thanh toán
            BadRequestException: Nếu giao dịch không ở trạng thái chờ xử lý
        """
        # Lấy thanh toán
        payment = await self.payment_repo.get(payment_id)
        if not payment:
            raise NotFoundException(f"Không tìm thấy thanh toán với ID {payment_id}")

        # Kiểm tra trạng thái
        if payment["status"] != "pending":
            raise BadRequestException(
                f"Không thể xử lý thanh toán với trạng thái {payment['status']}"
            )

        # Cập nhật trạng thái sang processing
        await self.payment_repo.update(payment_id, {"status": "processing"})

        # Lấy phương thức thanh toán
        payment_method = None
        if payment["payment_method_id"]:
            payment_method = await self.payment_method_repo.get(
                payment["payment_method_id"]
            )

        if not payment_method:
            # Cập nhật trạng thái sang failed
            await self.payment_repo.update(
                payment_id,
                {
                    "status": "failed",
                    "error_message": "Không tìm thấy phương thức thanh toán",
                    "completed_at": datetime.now().isoformat(),
                },
            )
            return {
                "success": False,
                "message": "Không tìm thấy phương thức thanh toán",
                "payment_id": payment_id,
            }

        # Xử lý thanh toán dựa trên loại phương thức thanh toán
        # Đây chỉ là mô phỏng, trong thực tế cần tích hợp với cổng thanh toán
        payment_type = payment_method["type"]
        provider = payment_method["provider"]

        try:
            # Mô phỏng xử lý thanh toán
            # Trong thực tế, cần gọi API của cổng thanh toán

            # Mô phỏng thanh toán thành công
            transaction_id = f"TX-{payment_id}-{int(datetime.now().timestamp())}"

            # Cập nhật trạng thái sang completed
            await self.payment_repo.update(
                payment_id,
                {
                    "status": "completed",
                    "transaction_id": transaction_id,
                    "completed_at": datetime.now().isoformat(),
                },
            )

            # Metrics
            self.metrics.track_user_activity("payment_completed", "system")

            return {
                "success": True,
                "message": "Thanh toán thành công",
                "payment_id": payment_id,
                "transaction_id": transaction_id,
            }
        except Exception as e:
            # Xử lý lỗi
            error_message = str(e)

            # Cập nhật trạng thái sang failed
            await self.payment_repo.update(
                payment_id,
                {
                    "status": "failed",
                    "error_message": error_message,
                    "completed_at": datetime.now().isoformat(),
                },
            )

            # Metrics
            self.metrics.track_user_activity("payment_failed", "system")

            return {
                "success": False,
                "message": "Thanh toán thất bại",
                "payment_id": payment_id,
                "error": error_message,
            }

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="payments", tags=["payment_details", "user_payments"])
    async def refund_payment(
        self, payment_id: int, reason: str, admin_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Hoàn tiền cho giao dịch thanh toán.

        Args:
            payment_id: ID của giao dịch thanh toán
            reason: Lý do hoàn tiền
            admin_id: ID của admin thực hiện hoàn tiền (tùy chọn)

        Returns:
            Thông tin giao dịch thanh toán đã hoàn tiền

        Raises:
            NotFoundException: Nếu không tìm thấy giao dịch thanh toán
            BadRequestException: Nếu giao dịch không thể hoàn tiền
        """
        # Lấy thanh toán
        payment = await self.payment_repo.get(payment_id)
        if not payment:
            raise NotFoundException(f"Không tìm thấy thanh toán với ID {payment_id}")

        # Kiểm tra quyền (chỉ admin có thể hoàn tiền)
        if admin_id:
            try:
                is_admin = await check_permission(admin_id, "manage_payments")
                if not is_admin:
                    raise ForbiddenException("Bạn không có quyền hoàn tiền thanh toán")
            except:
                raise ForbiddenException("Bạn không có quyền hoàn tiền thanh toán")

        # Kiểm tra trạng thái
        if payment["status"] != "completed":
            raise BadRequestException(
                f"Không thể hoàn tiền thanh toán với trạng thái {payment['status']}"
            )

        # Làm sạch dữ liệu
        reason = sanitize_html(reason)

        # Lưu trạng thái cũ
        before_state = dict(payment)

        # Cập nhật trạng thái
        updated_payment = await self.payment_repo.update(
            payment_id,
            {
                "status": "refunded",
                "refund_reason": reason,
                "refunded_at": datetime.now().isoformat(),
                "refunded_by": admin_id,
            },
        )

        # Ghi log hoạt động
        await self.user_log_service.log_activity(
            self.db,
            user_id=admin_id if admin_id else payment["user_id"],
            activity_type="REFUND_PAYMENT",
            resource_type="payment",
            resource_id=str(payment_id),
            before_state=before_state,
            after_state=dict(updated_payment),
            metadata={
                "reason": reason,
                "amount": payment["amount"],
                "currency": payment["currency"],
            },
        )

        # Metrics
        self.metrics.track_user_activity("refund_payment", "admin")

        # Gửi thông báo cho người dùng
        try:
            from app.user_site.services.notification_service import NotificationService

            notification_service = NotificationService(self.db)

            title = "Hoàn tiền thanh toán"
            message = f"Thanh toán {payment['amount']} {payment['currency']} cho {payment['purpose']} đã được hoàn tiền. Lý do: {reason}"

            await notification_service.create_notification(
                user_id=payment["user_id"],
                type="PAYMENT_REFUND",
                title=title,
                message=message,
                link=f"/payments/{payment_id}",
            )
        except Exception as e:
            # Log lỗi nhưng không fail request
            print(f"Lỗi khi gửi thông báo hoàn tiền: {str(e)}")

        return {
            "success": True,
            "message": "Đã hoàn tiền thanh toán thành công",
            "payment": updated_payment,
        }

    def _generate_reference_id(self, user_id: int) -> str:
        """Tạo mã tham chiếu cho thanh toán.

        Args:
            user_id: ID người dùng

        Returns:
            Mã tham chiếu
        """
        import uuid

        timestamp = int(datetime.now().timestamp())
        return f"PAY-{user_id}-{timestamp}-{str(uuid.uuid4())[:8]}"
