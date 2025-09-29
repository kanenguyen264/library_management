from typing import Optional, List, Dict, Any
from sqlalchemy import select, func, and_, desc, asc, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from decimal import Decimal
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError

from app.user_site.models.payment import Payment
from app.user_site.models.user import User
from app.user_site.models.subscription import UserSubscription
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    ValidationException,
)


class PaymentRepository:
    """Repository cho các thao tác với Giao dịch thanh toán (Payment)."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession.

        Args:
            db: Đối tượng AsyncSession để tương tác với cơ sở dữ liệu.
        """
        self.db = db

    async def create(self, user_id: int, data: Dict[str, Any]) -> Payment:
        """Tạo một giao dịch thanh toán mới.

        Args:
            user_id: ID của người dùng thực hiện giao dịch.
            data: Dữ liệu giao dịch. Các trường yêu cầu/tùy chọn:
                - amount (Decimal): Số tiền giao dịch.
                - currency (str): Đơn vị tiền tệ (ví dụ: 'VND').
                - payment_method (str): Phương thức thanh toán sử dụng.
                - status (str): Trạng thái giao dịch ('pending', 'completed', 'failed').
                - transaction_id (Optional[str]): ID giao dịch từ bên thứ ba.
                - subscription_id (Optional[int]): ID đăng ký liên quan (nếu có).
                - payment_gateway (Optional[str]): Cổng thanh toán sử dụng.
                - error_message (Optional[str]): Thông báo lỗi (nếu status='failed').

        Returns:
            Đối tượng PaymentTransaction đã tạo.

        Raises:
            NotFoundException: Nếu user_id hoặc subscription_id không tồn tại.
            ValidationException: Nếu thiếu thông tin bắt buộc hoặc amount không hợp lệ.
            ConflictException: Nếu có lỗi ràng buộc khác.
        """
        # Kiểm tra user
        user = await self.db.get(User, user_id)
        if not user:
            raise NotFoundException(f"Người dùng với ID {user_id} không tồn tại.")

        allowed_fields = {
            "amount",
            "currency",
            "payment_method",
            "status",
            "transaction_id",
            "subscription_id",
            "payment_gateway",
            "error_message",
        }
        filtered_data = {k: v for k, v in data.items() if k in allowed_fields}
        filtered_data["user_id"] = user_id

        # Validation
        amount_str = filtered_data.get("amount")
        if amount_str is None:
            raise ValidationException("Số tiền (amount) là bắt buộc.")
        try:
            amount = Decimal(str(amount_str))
            if amount <= 0:
                raise ValidationException("Số tiền (amount) phải lớn hơn 0.")
            filtered_data["amount"] = amount  # Lưu dưới dạng Decimal
        except Exception:
            raise ValidationException("Số tiền (amount) không hợp lệ.")

        if not filtered_data.get("currency"):
            raise ValidationException("Đơn vị tiền tệ (currency) là bắt buộc.")
        if not filtered_data.get("payment_method"):
            raise ValidationException(
                "Phương thức thanh toán (payment_method) là bắt buộc."
            )
        if not filtered_data.get("status"):
            filtered_data["status"] = "pending"  # Mặc định là pending

        sub_id = filtered_data.get("subscription_id")
        if sub_id:
            subscription = await self.db.get(UserSubscription, sub_id)
            if not subscription:
                raise NotFoundException(f"Đăng ký với ID {sub_id} không tồn tại.")
            # Kiểm tra subscription có thuộc user không?
            if subscription.user_id != user_id:
                raise ValidationException(
                    f"Đăng ký ID {sub_id} không thuộc người dùng ID {user_id}."
                )

        transaction = Payment(**filtered_data)
        self.db.add(transaction)
        try:
            await self.db.commit()
            await self.db.refresh(transaction)
            return transaction
        except IntegrityError as e:
            await self.db.rollback()
            # Có thể do transaction_id bị trùng?
            raise ConflictException(f"Không thể tạo giao dịch thanh toán: {e}")

    async def get_by_id(
        self, transaction_id: int, with_relations: bool = False
    ) -> Optional[Payment]:
        """Lấy giao dịch thanh toán theo ID nội bộ (PK).

        Args:
            transaction_id: ID của giao dịch.
            with_relations: Có load user và subscription không.

        Returns:
            Đối tượng PaymentTransaction hoặc None.
        """
        query = select(Payment).where(Payment.id == transaction_id)

        if with_relations:
            query = query.options(
                selectinload(Payment.user),
                selectinload(Payment.subscription),
            )

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_external_id(
        self, external_transaction_id: str
    ) -> Optional[Payment]:
        """Lấy giao dịch thanh toán theo transaction_id từ bên ngoài (ví dụ: từ cổng thanh toán).

        Args:
            external_transaction_id: ID giao dịch từ bên thứ ba.

        Returns:
            Đối tượng PaymentTransaction hoặc None.
        """
        query = select(Payment).where(Payment.transaction_id == external_transaction_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_by_user(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        with_relations: bool = False,
    ) -> List[Payment]:
        """Lấy danh sách giao dịch thanh toán của người dùng, có bộ lọc.

        Args:
            user_id: ID người dùng.
            skip, limit: Phân trang.
            status: Lọc theo trạng thái.
            start_date: Lọc từ ngày (bao gồm cả ngày đó).
            end_date: Lọc đến ngày (bao gồm cả ngày đó).
            with_relations: Có load subscription không.

        Returns:
            Danh sách PaymentTransaction.
        """
        query = select(Payment).where(Payment.user_id == user_id)

        if status:
            query = query.filter(Payment.status == status)
        if start_date:
            query = query.filter(Payment.created_at >= start_date)
        if end_date:
            # Đảm bảo bao gồm cả ngày kết thúc
            end_datetime = end_date + timedelta(days=1)
            query = query.filter(Payment.created_at < end_datetime)

        query = query.order_by(desc(Payment.created_at))
        query = query.offset(skip).limit(limit)

        if with_relations:
            # Chỉ cần load subscription, user đã biết
            query = query.options(selectinload(Payment.subscription))

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_by_user(
        self,
        user_id: int,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        """Đếm số lượng giao dịch thanh toán của người dùng, có bộ lọc.

        Args:
            user_id: ID người dùng.
            status: Lọc theo trạng thái.
            start_date: Lọc từ ngày.
            end_date: Lọc đến ngày.

        Returns:
            Số lượng giao dịch khớp điều kiện.
        """
        query = select(func.count(Payment.id)).where(Payment.user_id == user_id)

        if status:
            query = query.filter(Payment.status == status)
        if start_date:
            query = query.filter(Payment.created_at >= start_date)
        if end_date:
            end_datetime = end_date + timedelta(days=1)
            query = query.filter(Payment.created_at < end_datetime)

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def update(self, transaction_pk_id: int, data: Dict[str, Any]) -> Payment:
        """Cập nhật thông tin giao dịch thanh toán (dùng ID nội bộ).
           Thường dùng để cập nhật status, error_message, transaction_id từ cổng thanh toán.

        Args:
            transaction_pk_id: ID (PK) của giao dịch trong DB.
            data: Dữ liệu cập nhật.

        Returns:
            Đối tượng PaymentTransaction đã cập nhật.

        Raises:
            NotFoundException: Nếu không tìm thấy giao dịch.
            ConflictException: Nếu có lỗi ràng buộc.
        """
        transaction = await self.get_by_id(transaction_pk_id)
        if not transaction:
            raise NotFoundException(
                f"Không tìm thấy giao dịch thanh toán với ID {transaction_pk_id}"
            )

        allowed_fields = {
            "status",
            "error_message",
            "transaction_id",
            "payment_gateway",
        }  # Giới hạn trường cập nhật
        updated = False
        for key, value in data.items():
            # Chỉ cập nhật nếu trường cho phép và giá trị khác giá trị hiện tại
            if (
                key in allowed_fields
                and value is not None
                and getattr(transaction, key) != value
            ):
                setattr(transaction, key, value)
                updated = True

        if not updated:
            return transaction  # Không có gì thay đổi

        try:
            await self.db.commit()
            await self.db.refresh(transaction)
            return transaction
        except IntegrityError as e:
            await self.db.rollback()
            raise ConflictException(f"Lỗi khi cập nhật giao dịch: {e}")

    async def update_status(
        self, transaction_pk_id: int, status: str, error_message: Optional[str] = None
    ) -> Payment:
        """Cập nhật trạng thái giao dịch thanh toán (wrapper cho update)."""
        update_data = {"status": status}
        if error_message:
            update_data["error_message"] = error_message

        return await self.update(transaction_pk_id, update_data)

    async def get_user_total_spending(self, user_id: int) -> Decimal:
        """Tính tổng số tiền đã chi tiêu thành công của người dùng.

        Args:
            user_id: ID người dùng.

        Returns:
            Tổng số tiền (Decimal).
        """
        query = select(func.sum(Payment.amount)).where(
            Payment.user_id == user_id,
            Payment.status == "completed",  # Chỉ tính giao dịch thành công
        )
        result = await self.db.execute(query)
        total = (
            result.scalar_one()
        )  # Kết quả SUM có thể là None nếu không có giao dịch nào
        return total if total is not None else Decimal("0.00")

    async def get_transactions_by_subscription(
        self, subscription_id: int, limit: Optional[int] = None
    ) -> List[Payment]:
        """Lấy danh sách giao dịch thanh toán cho một đăng ký, sắp xếp theo ngày tạo mới nhất.

        Args:
            subscription_id: ID đăng ký.
            limit: Giới hạn số lượng (nếu cần).

        Returns:
            Danh sách PaymentTransaction.
        """
        query = select(Payment).where(Payment.subscription_id == subscription_id)
        query = query.order_by(desc(Payment.created_at))
        if limit:
            query = query.limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_latest_transaction(
        self, user_id: int, with_relations: bool = False
    ) -> Optional[Payment]:
        """Lấy giao dịch thanh toán mới nhất của người dùng.

        Args:
            user_id: ID người dùng.
            with_relations: Có load subscription không.

        Returns:
            Giao dịch mới nhất hoặc None.
        """
        query = select(Payment).where(Payment.user_id == user_id)
        query = query.order_by(desc(Payment.created_at)).limit(1)
        if with_relations:
            query = query.options(selectinload(Payment.subscription))

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_payment_statistics(self, user_id: int) -> Dict[str, Any]:
        """Lấy thống kê thanh toán cơ bản của người dùng.

        Returns:
            Dict chứa total_spending, completed_count, failed_count.
        """
        # Tổng chi tiêu
        total_spending = await self.get_user_total_spending(user_id)

        # Đếm theo trạng thái
        count_query = (
            select(
                Payment.status,
                func.count(Payment.id).label("count"),
            )
            .where(Payment.user_id == user_id)
            .group_by(Payment.status)
        )

        count_result = await self.db.execute(count_query)
        status_counts = {row.status: row.count for row in count_result}

        return {
            "total_spending": total_spending,
            "completed_count": status_counts.get("completed", 0),
            "failed_count": status_counts.get("failed", 0),
            "pending_count": status_counts.get("pending", 0),
        }

    async def record_subscription_payment(
        self,
        user_id: int,
        subscription_id: int,
        amount: Decimal,
        currency: str,
        payment_method: str,
        status: str = "completed",  # Trạng thái mặc định là completed
        transaction_id: Optional[str] = None,
        payment_gateway: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Payment:
        """Ghi nhận một thanh toán cho đăng ký (wrapper cho create)."""
        data = {
            "amount": amount,
            "currency": currency,
            "payment_method": payment_method,
            "status": status,
            "subscription_id": subscription_id,
            "transaction_id": transaction_id,
            "payment_gateway": payment_gateway,
            "error_message": error_message,
        }
        return await self.create(user_id, data)
