from typing import Optional, List, Dict, Any
from sqlalchemy import select, update, delete, func, or_, and_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload  # Dùng selectinload nếu cần load user
from sqlalchemy.exc import IntegrityError

from app.user_site.models.payment import PaymentMethod
from app.user_site.models.user import User  # Để kiểm tra user_id
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    ValidationException,
)


class PaymentMethodRepository:
    """Repository cho các thao tác với Phương thức thanh toán (PaymentMethod) của người dùng."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession.

        Args:
            db: Đối tượng AsyncSession để tương tác với cơ sở dữ liệu.
        """
        self.db = db

    async def create(self, user_id: int, data: Dict[str, Any]) -> PaymentMethod:
        """Tạo mới phương thức thanh toán cho người dùng.

        Args:
            user_id: ID của người dùng sở hữu phương thức này.
            data: Dữ liệu phương thức thanh toán. Các trường có thể bao gồm:
                - method_type (str): Loại phương thức (ví dụ: 'card', 'paypal').
                - details (Dict[str, Any]): Chi tiết phương thức (số thẻ che, tên chủ thẻ, hết hạn...). Lưu dưới dạng JSON.
                - provider_token (Optional[str]): Token từ nhà cung cấp dịch vụ thanh toán.
                - is_default (bool): Có phải là phương thức mặc định không (mặc định False).
                - is_active (bool): Phương thức có đang hoạt động không (mặc định True).
                - is_verified (bool): Đã được xác minh chưa (mặc định False).

        Returns:
            Đối tượng PaymentMethod đã tạo.

        Raises:
            NotFoundException: Nếu user_id không tồn tại.
            ValidationException: Nếu thiếu thông tin bắt buộc.
            ConflictException: Nếu có lỗi ràng buộc khác.
        """
        # Kiểm tra user tồn tại
        user = await self.db.get(User, user_id)
        if not user:
            raise NotFoundException(f"Người dùng với ID {user_id} không tồn tại.")

        allowed_fields = {
            "method_type",
            "details",
            "provider_token",
            "is_default",
            "is_active",
            "is_verified",
        }
        filtered_data = {k: v for k, v in data.items() if k in allowed_fields}
        filtered_data["user_id"] = user_id

        # Validation cơ bản
        if not filtered_data.get("method_type") or not filtered_data.get("details"):
            raise ValidationException(
                "Loại phương thức (method_type) và chi tiết (details) là bắt buộc."
            )

        filtered_data.setdefault("is_default", False)
        filtered_data.setdefault("is_active", True)
        filtered_data.setdefault("is_verified", False)

        # Nếu đặt làm mặc định, cần hủy mặc định các phương thức khác
        if filtered_data["is_default"]:
            await self._unset_other_defaults(user_id)

        payment_method = PaymentMethod(**filtered_data)
        self.db.add(payment_method)
        try:
            await self.db.commit()
            await self.db.refresh(payment_method)
            return payment_method
        except IntegrityError as e:
            await self.db.rollback()
            raise ConflictException(f"Không thể tạo phương thức thanh toán: {e}")

    async def get_by_id(
        self, payment_method_id: int, user_id: Optional[int] = None
    ) -> Optional[PaymentMethod]:
        """Lấy phương thức thanh toán theo ID.

        Args:
            payment_method_id: ID của phương thức thanh toán.
            user_id: (Tùy chọn) ID người dùng để kiểm tra quyền sở hữu.

        Returns:
            Phương thức thanh toán hoặc None nếu không tìm thấy hoặc không thuộc user_id.
        """
        query = select(PaymentMethod).where(PaymentMethod.id == payment_method_id)
        if user_id is not None:
            query = query.where(PaymentMethod.user_id == user_id)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def update(
        self, payment_method_id: int, user_id: int, data: Dict[str, Any]
    ) -> PaymentMethod:
        """Cập nhật phương thức thanh toán.
           Chỉ cho phép cập nhật các trường như details (hạn thẻ), is_default.

        Args:
            payment_method_id: ID của phương thức thanh toán.
            user_id: ID của người dùng sở hữu.
            data: Dữ liệu cập nhật (ví dụ: {'details': {...}, 'is_default': True}).

        Returns:
            Phương thức thanh toán đã cập nhật.

        Raises:
            NotFoundException: Nếu không tìm thấy phương thức thanh toán hoặc không thuộc về người dùng.
            ValidationException: Nếu dữ liệu cập nhật không hợp lệ.
            ConflictException: Nếu có lỗi ràng buộc.
        """
        payment_method = await self.get_by_id(payment_method_id, user_id=user_id)
        if not payment_method:
            raise NotFoundException(
                f"Không tìm thấy phương thức thanh toán ID {payment_method_id} cho người dùng ID {user_id}."
            )

        allowed_fields = {
            "details",
            "is_default",
        }  # Giới hạn các trường có thể cập nhật
        updated = False
        new_default_status = data.get("is_default")

        for key, value in data.items():
            if (
                key in allowed_fields
                and value is not None
                and getattr(payment_method, key) != value
            ):
                setattr(payment_method, key, value)
                updated = True

        if not updated:
            return payment_method  # Không có gì thay đổi

        # Xử lý is_default
        if new_default_status is True and not payment_method.is_default:
            # Đặt làm mặc định
            await self._unset_other_defaults(user_id, exclude_id=payment_method_id)
            payment_method.is_default = True  # Đảm bảo nó được set lại
        elif new_default_status is False and payment_method.is_default:
            # Bỏ mặc định -> Cần đảm bảo có cái khác làm mặc định nếu đây là cái duy nhất
            # Tuy nhiên, logic này phức tạp, có lẽ nên dùng hàm set_default_method riêng
            raise ValidationException(
                "Không thể bỏ mặc định trực tiếp. Sử dụng hàm set_default_method cho phương thức khác."
            )

        try:
            await self.db.commit()
            await self.db.refresh(payment_method)
            return payment_method
        except IntegrityError as e:
            await self.db.rollback()
            raise ConflictException(f"Lỗi khi cập nhật phương thức thanh toán: {e}")

    async def delete(self, payment_method_id: int, user_id: int) -> bool:
        """Xóa (hoặc thường là vô hiệu hóa) phương thức thanh toán.
           Để an toàn, nên dùng deactivate_method thay vì xóa cứng.

        Args:
            payment_method_id: ID của phương thức thanh toán.
            user_id: ID của người dùng sở hữu.

        Returns:
            True nếu xóa thành công, False nếu không tìm thấy.
        """
        payment_method = await self.get_by_id(payment_method_id, user_id=user_id)
        if not payment_method:
            return False

        # Cân nhắc: Nếu là default thì không cho xóa? Hoặc đặt cái khác làm default?
        if payment_method.is_default:
            raise ValidationException(
                "Không thể xóa phương thức thanh toán mặc định. Vui lòng đặt phương thức khác làm mặc định trước."
            )

        await self.db.delete(payment_method)
        await self.db.commit()
        return True

    async def list_by_user(
        self, user_id: int, skip: int = 0, limit: int = 20
    ) -> List[PaymentMethod]:
        """Lấy danh sách các phương thức thanh toán đang hoạt động của người dùng.
           Sắp xếp mặc định lên trước.

        Args:
            user_id: ID của người dùng.
            skip: Số lượng bản ghi bỏ qua.
            limit: Số lượng bản ghi tối đa trả về.

        Returns:
            Danh sách PaymentMethod.
        """
        query = select(PaymentMethod).where(
            PaymentMethod.user_id == user_id,
            PaymentMethod.is_active == True,  # Chỉ lấy các phương thức đang hoạt động
        )
        query = query.order_by(
            PaymentMethod.is_default.desc(), PaymentMethod.created_at.desc()
        )
        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_by_user(self, user_id: int) -> int:
        """Đếm số lượng phương thức thanh toán đang hoạt động của người dùng.

        Args:
            user_id: ID của người dùng.

        Returns:
            Số lượng phương thức thanh toán hoạt động.
        """
        query = select(func.count(PaymentMethod.id)).where(
            PaymentMethod.user_id == user_id, PaymentMethod.is_active == True
        )
        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def get_default_method(self, user_id: int) -> Optional[PaymentMethod]:
        """Lấy phương thức thanh toán mặc định đang hoạt động của người dùng.

        Args:
            user_id: ID của người dùng.

        Returns:
            Phương thức thanh toán mặc định hoặc None nếu không có.
        """
        query = select(PaymentMethod).where(
            PaymentMethod.user_id == user_id,
            PaymentMethod.is_default == True,
            PaymentMethod.is_active == True,
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def _unset_other_defaults(
        self, user_id: int, exclude_id: Optional[int] = None
    ):
        """(Nội bộ) Hủy trạng thái mặc định của các phương thức khác cho user."""
        stmt = update(PaymentMethod).where(
            PaymentMethod.user_id == user_id, PaymentMethod.is_default == True
        )
        if exclude_id is not None:
            stmt = stmt.where(PaymentMethod.id != exclude_id)
        stmt = stmt.values(is_default=False).execution_options(
            synchronize_session=False
        )
        await self.db.execute(stmt)
        # Không commit ở đây, để hàm gọi commit chung

    async def set_default_method(self, payment_method_id: int, user_id: int) -> bool:
        """Đặt phương thức thanh toán làm mặc định cho người dùng.

        Args:
            payment_method_id: ID của phương thức thanh toán cần đặt làm mặc định.
            user_id: ID của người dùng sở hữu.

        Returns:
            True nếu thực hiện thành công.

        Raises:
            NotFoundException: Nếu không tìm thấy phương thức thanh toán hoặc không thuộc về người dùng.
        """
        payment_method = await self.get_by_id(payment_method_id, user_id=user_id)
        if not payment_method:
            raise NotFoundException(
                f"Không tìm thấy phương thức thanh toán ID {payment_method_id} cho người dùng ID {user_id}."
            )

        if payment_method.is_default:
            return True  # Đã là mặc định rồi

        # Hủy mặc định của tất cả phương thức thanh toán khác (trong cùng transaction)
        await self._unset_other_defaults(user_id, exclude_id=payment_method_id)

        # Đặt phương thức hiện tại làm mặc định
        payment_method.is_default = True

        await self.db.commit()
        return True

    async def deactivate_method(self, payment_method_id: int, user_id: int) -> bool:
        """Vô hiệu hóa (đánh dấu is_active=False) một phương thức thanh toán.
           Nếu đó là phương thức mặc định, sẽ cố gắng đặt phương thức hoạt động khác làm mặc định.

        Args:
            payment_method_id: ID của phương thức thanh toán.
            user_id: ID của người dùng sở hữu.

        Returns:
            True nếu thực hiện thành công.

        Raises:
            NotFoundException: Nếu không tìm thấy phương thức thanh toán hoặc không thuộc về người dùng.
        """
        payment_method = await self.get_by_id(payment_method_id, user_id=user_id)
        if not payment_method:
            raise NotFoundException(
                f"Không tìm thấy phương thức thanh toán ID {payment_method_id} cho người dùng ID {user_id}."
            )

        if not payment_method.is_active:
            return True  # Đã bị vô hiệu hóa rồi

        was_default = payment_method.is_default

        # Vô hiệu hóa
        payment_method.is_active = False
        payment_method.is_default = False  # Không thể là default nếu không active

        # Nếu nó từng là default, tìm cái khác thay thế
        new_default_set = False
        if was_default:
            other_active_methods = await self.list_by_user(
                user_id, limit=1
            )  # Lấy 1 cái active khác
            if other_active_methods:
                other_method = other_active_methods[0]
                # Chỉ set default nếu nó chưa phải default (tránh commit không cần thiết)
                if not other_method.is_default:
                    other_method.is_default = True
                    new_default_set = True

        await self.db.commit()
        return True

    async def verify_method(self, payment_method_id: int, user_id: int) -> bool:
        """Đánh dấu phương thức thanh toán đã được xác minh.

        Args:
            payment_method_id: ID của phương thức thanh toán.
            user_id: ID của người dùng sở hữu.

        Returns:
            True nếu cập nhật thành công, False nếu không tìm thấy hoặc đã xác minh.

        Raises:
            NotFoundException: Nếu không tìm thấy phương thức thanh toán hoặc không thuộc về người dùng.
        """
        payment_method = await self.get_by_id(payment_method_id, user_id=user_id)
        if not payment_method:
            raise NotFoundException(
                f"Không tìm thấy phương thức thanh toán ID {payment_method_id} cho người dùng ID {user_id}."
            )

        if payment_method.is_verified:
            return False  # Đã xác minh rồi

        payment_method.is_verified = True
        await self.db.commit()
        return True
