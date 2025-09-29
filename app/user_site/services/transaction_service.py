from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from uuid import uuid4
import logging
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc, text, asc
from fastapi import Depends, HTTPException, status

from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    InvalidOperationException,
    ServerException,
    UnauthorizedException,
)
from app.common.exceptions import ResourceNotFound, AuthorizationError
from app.common.db.session import get_db
from app.user_site.models.transaction import (
    Transaction,
    TransactionType,
    TransactionStatus,
)
from app.user_site.models.user import User
from app.user_site.schemas.transaction import (
    TransactionCreate,
    TransactionUpdate,
    TransactionResponse,
    TransactionListResponse,
    TransactionFilterParams,
    TransactionSummaryResponse,
    TransactionStatisticsResponse,
    PaymentRequest,
    PaymentResponse,
    RefundRequest,
    TransactionType,
    TransactionStatus,
    PaymentMethod,
    EntityType,
)
from app.cache.decorators import cached
from app.logs_manager.services.admin_activity_log_service import (
    create_admin_activity_log,
)
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate


logger = logging.getLogger(__name__)


class TransactionService:
    """Service để quản lý các giao dịch tài chính."""

    def __init__(self, db: Session = Depends(get_db)):
        self.db = db

    @staticmethod
    def create_transaction(
        db: Session,
        data: TransactionCreate,
        user_id: int,
        admin_id: Optional[int] = None,
    ) -> Transaction:
        """
        Create a new transaction in the database.

        Args:
            db: Database session
            data: Transaction data
            user_id: ID of the user making the transaction
            admin_id: Optional ID of admin creating transaction on behalf of user

        Returns:
            Created transaction object
        """
        try:
            transaction_data = data.dict()
            transaction = Transaction(**transaction_data, user_id=user_id)

            db.add(transaction)
            db.commit()
            db.refresh(transaction)

            if admin_id:
                create_admin_activity_log(
                    db=db,
                    log_data=AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="transaction_create",
                        entity_type="transaction",
                        entity_id=transaction.id,
                        description=f"Created transaction: {transaction.reference_code}",
                        metadata={
                            "user_id": user_id,
                            "amount": float(data.amount),
                            "transaction_type": data.transaction_type.value,
                            "status": transaction.status.value,
                        },
                    ),
                )

            return transaction
        except Exception as e:
            db.rollback()
            raise ServerException(f"Failed to create transaction: {str(e)}")

    @staticmethod
    def get_transaction_by_id(
        db: Session, transaction_id: int, user_id: Optional[int] = None
    ) -> Transaction:
        """
        Get transaction by ID.

        Args:
            db: Database session
            transaction_id: ID of the transaction to retrieve
            user_id: Optional user ID to verify ownership

        Returns:
            Transaction object

        Raises:
            NotFoundException: If transaction not found
            UnauthorizedException: If user_id doesn't match transaction's user_id
        """
        transaction = (
            db.query(Transaction).filter(Transaction.id == transaction_id).first()
        )

        if not transaction:
            raise NotFoundException(f"Transaction with ID {transaction_id} not found")

        if user_id and transaction.user_id != user_id:
            raise UnauthorizedException(
                "You do not have permission to access this transaction"
            )

        return transaction

    @staticmethod
    def get_transaction_by_reference(db: Session, reference_code: str) -> Transaction:
        """
        Get transaction by reference code.

        Args:
            db: Database session
            reference_code: Unique reference code of the transaction

        Returns:
            Transaction object

        Raises:
            NotFoundException: If transaction not found
        """
        transaction = (
            db.query(Transaction)
            .filter(Transaction.reference_code == reference_code)
            .first()
        )

        if not transaction:
            raise NotFoundException(
                f"Transaction with reference code {reference_code} not found"
            )

        return transaction

    @staticmethod
    def get_user_transactions(
        db: Session,
        user_id: int,
        filters: Optional[TransactionFilterParams] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Transaction], int]:
        """
        Get transactions for a specific user with optional filters.

        Args:
            db: Database session
            user_id: ID of the user
            filters: Optional filter parameters
            skip: Number of records to skip for pagination
            limit: Maximum number of records to return

        Returns:
            Tuple of (list of transactions, total count)
        """
        query = db.query(Transaction).filter(Transaction.user_id == user_id)

        # Apply filters if provided
        if filters:
            if filters.transaction_type:
                query = query.filter(
                    Transaction.transaction_type == filters.transaction_type
                )

            if filters.status:
                query = query.filter(Transaction.status == filters.status)

            if filters.payment_method:
                query = query.filter(
                    Transaction.payment_method == filters.payment_method
                )

            if filters.related_entity_type:
                query = query.filter(
                    Transaction.related_entity_type == filters.related_entity_type
                )

            if filters.related_entity_id:
                query = query.filter(
                    Transaction.related_entity_id == filters.related_entity_id
                )

            if filters.min_amount is not None:
                query = query.filter(Transaction.amount >= filters.min_amount)

            if filters.max_amount is not None:
                query = query.filter(Transaction.amount <= filters.max_amount)

            if filters.start_date:
                query = query.filter(Transaction.created_at >= filters.start_date)

            if filters.end_date:
                # Include the entire end date
                end_datetime = datetime.combine(filters.end_date, datetime.max.time())
                query = query.filter(Transaction.created_at <= end_datetime)

        # Get total count before pagination
        total_count = query.count()

        # Apply sorting and pagination
        transactions = (
            query.order_by(desc(Transaction.created_at)).offset(skip).limit(limit).all()
        )

        return transactions, total_count

    @staticmethod
    def update_transaction(
        db: Session,
        transaction_id: int,
        data: TransactionUpdate,
        admin_id: Optional[int] = None,
    ) -> Transaction:
        """
        Update an existing transaction.

        Args:
            db: Database session
            transaction_id: ID of the transaction to update
            data: Updated data
            admin_id: Optional ID of admin performing the update

        Returns:
            Updated transaction object

        Raises:
            NotFoundException: If transaction not found
            BadRequestException: If trying to update a completed transaction
        """
        transaction = TransactionService.get_transaction_by_id(db, transaction_id)

        # Prevent updating completed transactions unless explicitly allowed
        if transaction.is_completed and not getattr(data, "force_update", False):
            raise BadRequestException(
                "Cannot update a completed transaction. Set force_update=True to override."
            )

        update_data = data.model_dump(exclude_unset=True)

        # Remove force_update as it's not a database field
        if "force_update" in update_data:
            del update_data["force_update"]

        for key, value in update_data.items():
            setattr(transaction, key, value)

        # Special handling for status changes
        if "status" in update_data:
            if update_data["status"] == TransactionStatus.COMPLETED:
                transaction.completed_at = datetime.utcnow()

        db.commit()
        db.refresh(transaction)

        if admin_id:
            create_admin_activity_log(
                db=db,
                log_data=AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="transaction_update",
                    entity_type="transaction",
                    entity_id=transaction.id,
                    description=f"Updated transaction: {transaction.reference_code}",
                    metadata={
                        "updated_fields": list(update_data.keys()),
                        "new_status": (
                            transaction.status.value
                            if "status" in update_data
                            else None
                        ),
                    },
                ),
            )

        return transaction

    @staticmethod
    def process_payment(
        db: Session,
        transaction_id: int,
        payment_data: Dict[str, Any],
        admin_id: Optional[int] = None,
    ) -> Transaction:
        """
        Process a payment for a transaction.

        Args:
            db: Database session
            transaction_id: ID of the transaction
            payment_data: Payment gateway response data
            admin_id: Optional ID of admin processing the payment

        Returns:
            Updated transaction object
        """
        transaction = TransactionService.get_transaction_by_id(db, transaction_id)

        if transaction.status != TransactionStatus.PENDING:
            raise BadRequestException(
                f"Cannot process payment for transaction with status {transaction.status.value}"
            )

        # Update transaction with payment information
        transaction.gateway_response = payment_data

        # Determine if payment was successful based on gateway response
        if payment_data.get("status") == "success":
            transaction.status = TransactionStatus.COMPLETED
            transaction.completed_at = datetime.utcnow()
        elif payment_data.get("status") == "failed":
            transaction.status = TransactionStatus.FAILED

        db.commit()
        db.refresh(transaction)

        if admin_id:
            create_admin_activity_log(
                db=db,
                log_data=AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="payment_process",
                    entity_type="transaction",
                    entity_id=transaction.id,
                    description=f"Processed payment for transaction: {transaction.reference_code}",
                    metadata={
                        "payment_status": payment_data.get("status"),
                        "transaction_status": transaction.status.value,
                    },
                ),
            )

        return transaction

    @staticmethod
    def create_refund(
        db: Session,
        original_transaction_id: int,
        refund_reason: str,
        amount: Optional[float] = None,
        admin_id: Optional[int] = None,
    ) -> Transaction:
        """
        Create a refund transaction based on an original transaction.

        Args:
            db: Database session
            original_transaction_id: ID of the original transaction
            refund_reason: Reason for the refund
            amount: Optional refund amount (defaults to full amount if not specified)
            admin_id: Optional ID of admin creating the refund

        Returns:
            Created refund transaction
        """
        original_transaction = TransactionService.get_transaction_by_id(
            db, original_transaction_id
        )

        if original_transaction.status != TransactionStatus.COMPLETED:
            raise BadRequestException(
                f"Cannot refund transaction with status {original_transaction.status.value}"
            )

        # Determine refund amount
        refund_amount = (
            Decimal(str(amount)) if amount is not None else original_transaction.amount
        )

        # Create refund transaction
        refund_transaction = Transaction(
            user_id=original_transaction.user_id,
            amount=-abs(refund_amount),  # Ensure negative amount for refunds
            currency=original_transaction.currency,
            transaction_type=TransactionType.REFUND,
            status=TransactionStatus.PENDING,
            payment_method=original_transaction.payment_method,
            description=f"Refund for transaction #{original_transaction.id}",
            metadata=original_transaction.transaction_metadata,
            original_transaction_id=original_transaction.id,
            refund_reason=refund_reason,
            related_entity_type=original_transaction.related_entity_type,
            related_entity_id=original_transaction.related_entity_id,
        )

        db.add(refund_transaction)
        db.commit()
        db.refresh(refund_transaction)

        # Update original transaction status
        original_transaction.status = TransactionStatus.REFUNDED
        db.commit()

        if admin_id:
            create_admin_activity_log(
                db=db,
                log_data=AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="refund_create",
                    entity_type="transaction",
                    entity_id=refund_transaction.id,
                    description=f"Created refund transaction: {refund_transaction.reference_code}",
                    metadata={
                        "original_transaction_id": original_transaction.id,
                        "refund_amount": float(refund_amount),
                        "refund_reason": refund_reason,
                    },
                ),
            )

        return refund_transaction

    @staticmethod
    def get_user_balance(db: Session, user_id: int) -> float:
        """
        Calculate current balance for a user based on all transactions.

        Args:
            db: Database session
            user_id: ID of the user

        Returns:
            User's current balance
        """
        result = (
            db.query(func.sum(Transaction.amount))
            .filter(
                Transaction.user_id == user_id,
                Transaction.status == TransactionStatus.COMPLETED,
            )
            .scalar()
        )

        return float(result or 0)

    @staticmethod
    @cached(ttl=3600, key_prefix="transaction_stats")
    def get_transaction_statistics(db: Session, days: int = 30) -> Dict[str, Any]:
        """
        Get transaction statistics for the past number of days.

        Args:
            db: Database session
            days: Number of days to include in statistics

        Returns:
            Dictionary containing transaction statistics
        """
        start_date = datetime.utcnow() - timedelta(days=days)

        # Total transactions by type
        transactions_by_type = (
            db.query(
                Transaction.transaction_type,
                func.count(Transaction.id).label("count"),
                func.sum(Transaction.amount).label("amount"),
            )
            .filter(Transaction.created_at >= start_date)
            .group_by(Transaction.transaction_type)
            .all()
        )

        # Total transactions by status
        transactions_by_status = (
            db.query(Transaction.status, func.count(Transaction.id).label("count"))
            .filter(Transaction.created_at >= start_date)
            .group_by(Transaction.status)
            .all()
        )

        # Format the results
        by_type = {
            t_type.value: {"count": count, "amount": float(amount or 0)}
            for t_type, count, amount in transactions_by_type
        }

        by_status = {status.value: count for status, count in transactions_by_status}

        # Calculate totals
        total_count = sum(by_status.values())
        total_amount = sum(data["amount"] for data in by_type.values())

        return {
            "total_count": total_count,
            "total_amount": float(total_amount),
            "by_type": by_type,
            "by_status": by_status,
            "period_days": days,
        }

    def get_transaction(
        self, transaction_id: int, user_id: Optional[int] = None
    ) -> TransactionResponse:
        """Lấy thông tin giao dịch theo ID."""
        query = self.db.query(Transaction).filter(Transaction.id == transaction_id)

        if user_id:
            query = query.filter(Transaction.user_id == user_id)

        transaction = query.first()

        if not transaction:
            raise ResourceNotFound(
                message="Không tìm thấy giao dịch",
                resource_type="Transaction",
                resource_id=str(transaction_id),
            )

        return TransactionResponse.model_validate(transaction)

    def update_transaction(
        self,
        transaction_id: int,
        data: TransactionUpdate,
        user_id: Optional[int] = None,
    ) -> TransactionResponse:
        """Cập nhật thông tin giao dịch."""
        query = self.db.query(Transaction).filter(Transaction.id == transaction_id)

        if user_id:
            query = query.filter(Transaction.user_id == user_id)

        transaction = query.first()

        if not transaction:
            raise ResourceNotFound(
                message="Không tìm thấy giao dịch",
                resource_type="Transaction",
                resource_id=str(transaction_id),
            )

        # Cập nhật các trường từ data
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(transaction, field, value)

        self.db.commit()
        self.db.refresh(transaction)

        return TransactionResponse.model_validate(transaction)

    def delete_transaction(
        self, transaction_id: int, user_id: Optional[int] = None
    ) -> bool:
        """Xóa giao dịch."""
        query = self.db.query(Transaction).filter(Transaction.id == transaction_id)

        if user_id:
            query = query.filter(Transaction.user_id == user_id)

        transaction = query.first()

        if not transaction:
            raise ResourceNotFound(
                message="Không tìm thấy giao dịch",
                resource_type="Transaction",
                resource_id=str(transaction_id),
            )

        self.db.delete(transaction)
        self.db.commit()

        return True

    def get_user_transactions(
        self,
        user_id: int,
        filters: Optional[TransactionFilterParams] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> TransactionListResponse:
        """Lấy danh sách giao dịch của người dùng."""
        query = self.db.query(Transaction).filter(Transaction.user_id == user_id)

        if filters:
            if filters.transaction_type:
                query = query.filter(
                    Transaction.transaction_type == filters.transaction_type
                )

            if filters.status:
                query = query.filter(Transaction.status == filters.status)

            if filters.payment_method:
                query = query.filter(
                    Transaction.payment_method == filters.payment_method
                )

            if filters.min_amount is not None:
                query = query.filter(Transaction.amount >= filters.min_amount)

            if filters.max_amount is not None:
                query = query.filter(Transaction.amount <= filters.max_amount)

            if filters.start_date:
                query = query.filter(Transaction.created_at >= filters.start_date)

            if filters.end_date:
                query = query.filter(Transaction.created_at <= filters.end_date)

            if filters.related_entity_type:
                query = query.filter(
                    Transaction.related_entity_type == filters.related_entity_type
                )

            if filters.related_entity_id:
                query = query.filter(
                    Transaction.related_entity_id == filters.related_entity_id
                )

            if filters.sort_by:
                if filters.sort_desc:
                    query = query.order_by(getattr(Transaction, filters.sort_by).desc())
                else:
                    query = query.order_by(getattr(Transaction, filters.sort_by))
        else:
            # Mặc định sắp xếp theo thời gian giao dịch (mới nhất trước)
            query = query.order_by(Transaction.created_at.desc())

        # Tính tổng số giao dịch
        total = query.count()

        # Áp dụng phân trang
        query = query.offset((page - 1) * page_size).limit(page_size)

        transactions = query.all()

        return TransactionListResponse(
            items=[TransactionResponse.model_validate(t) for t in transactions],
            total=total,
            page=page,
            size=page_size,
        )

    @cached(key_prefix="transaction_summary", ttl=3600)  # Cache 1 giờ
    def get_user_transaction_summary(self, user_id: int) -> TransactionSummaryResponse:
        """Lấy tổng hợp giao dịch của người dùng."""
        # Kiểm tra người dùng tồn tại
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ResourceNotFound(
                message="Không tìm thấy người dùng",
                resource_type="User",
                resource_id=str(user_id),
            )

        # Tổng số tiền giao dịch theo loại
        total_by_type = {}
        types = ["payment", "refund", "subscription", "purchase", "reward"]

        for t_type in types:
            total = (
                self.db.query(func.sum(Transaction.amount))
                .filter(
                    Transaction.user_id == user_id,
                    Transaction.transaction_type == t_type,
                    Transaction.status == "completed",
                )
                .scalar()
                or 0
            )

            total_by_type[t_type] = float(total)

        # Tổng số giao dịch theo trạng thái
        status_counts = {}
        statuses = ["pending", "completed", "failed", "refunded", "cancelled"]

        for status in statuses:
            count = (
                self.db.query(func.count(Transaction.id))
                .filter(Transaction.user_id == user_id, Transaction.status == status)
                .scalar()
                or 0
            )

            status_counts[status] = count

        # Thống kê theo tháng (6 tháng gần nhất)
        monthly_stats = {}
        current_date = datetime.now()

        for i in range(6):
            month = (current_date.month - i) % 12 or 12
            year = current_date.year - ((current_date.month - i - 1) // 12)
            month_name = f"{year}-{month:02d}"

            # Tổng số tiền giao dịch hoàn thành trong tháng
            total = (
                self.db.query(func.sum(Transaction.amount))
                .filter(
                    Transaction.user_id == user_id,
                    Transaction.status == "completed",
                    func.extract("year", Transaction.created_at) == year,
                    func.extract("month", Transaction.created_at) == month,
                )
                .scalar()
                or 0
            )

            # Số lượng giao dịch trong tháng
            count = (
                self.db.query(func.count(Transaction.id))
                .filter(
                    Transaction.user_id == user_id,
                    func.extract("year", Transaction.created_at) == year,
                    func.extract("month", Transaction.created_at) == month,
                )
                .scalar()
                or 0
            )

            monthly_stats[month_name] = {
                "total_amount": float(total),
                "transaction_count": count,
            }

        # Lấy giao dịch gần nhất
        recent_transactions = (
            self.db.query(Transaction)
            .filter(Transaction.user_id == user_id)
            .order_by(Transaction.created_at.desc())
            .limit(5)
            .all()
        )

        return TransactionSummaryResponse(
            total_transactions=sum(status_counts.values()),
            total_amount=sum(total_by_type.values()),
            by_type=total_by_type,
            by_status=status_counts,
            monthly_stats=monthly_stats,
            recent_transactions=[
                TransactionResponse.model_validate(t) for t in recent_transactions
            ],
        )

    def process_payment(
        self,
        user_id: int,
        amount: float,
        payment_method: str,
        description: str,
        metadata: Dict[str, Any] = None,
    ) -> TransactionResponse:
        """Xử lý thanh toán."""
        # Kiểm tra người dùng
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ResourceNotFound(
                message="Không tìm thấy người dùng",
                resource_type="User",
                resource_id=str(user_id),
            )

        # Thực hiện logic xử lý thanh toán ở đây
        # Ví dụ: Tích hợp với cổng thanh toán, xác thực, v.v.

        # Tạo bản ghi giao dịch mới
        transaction = Transaction(
            user_id=user_id,
            amount=amount,
            currency="VND",  # Có thể lấy từ cấu hình hoặc tham số
            transaction_type="payment",
            status="pending",  # Ban đầu đặt trạng thái là pending
            payment_method=payment_method,
            description=description,
            metadata=metadata or {},
        )

        self.db.add(transaction)
        self.db.commit()
        self.db.refresh(transaction)

        # TODO: Thực hiện xử lý thanh toán thực tế với cổng thanh toán
        # Sau khi xử lý thành công, cập nhật trạng thái giao dịch

        return TransactionResponse.model_validate(transaction)

    def process_refund(
        self,
        transaction_id: int,
        amount: Optional[float] = None,
        reason: str = "Yêu cầu hoàn tiền",
    ) -> TransactionResponse:
        """Xử lý hoàn tiền."""
        transaction = (
            self.db.query(Transaction).filter(Transaction.id == transaction_id).first()
        )

        if not transaction:
            raise ResourceNotFound(
                message="Không tìm thấy giao dịch",
                resource_type="Transaction",
                resource_id=str(transaction_id),
            )

        if transaction.status != "completed":
            raise InvalidOperationException(
                detail="Chỉ có thể hoàn tiền cho giao dịch đã hoàn thành",
                field="status",
            )

        refund_amount = amount if amount is not None else transaction.amount

        if refund_amount > transaction.amount:
            raise BadRequestException(
                detail="Số tiền hoàn lại không thể lớn hơn số tiền giao dịch ban đầu",
                field="amount",
            )

        # Tạo giao dịch hoàn tiền mới
        refund_transaction = Transaction(
            user_id=transaction.user_id,
            amount=refund_amount,
            currency=transaction.currency,
            transaction_type="refund",
            status="pending",
            payment_method=transaction.payment_method,
            description=f"Hoàn tiền cho giao dịch #{transaction.id}: {reason}",
            metadata={
                "original_transaction_id": transaction.id,
                "reason": reason,
                "refund_amount": refund_amount,
            },
            related_entity_id=transaction.id,
            related_entity_type="transaction",
        )

        self.db.add(refund_transaction)

        # Cập nhật trạng thái giao dịch gốc
        transaction.status = "refunded"
        transaction.metadata = {
            **(transaction.metadata or {}),
            "refund_transaction_id": refund_transaction.id,
            "refund_amount": refund_amount,
            "refund_reason": reason,
            "refund_date": datetime.now().isoformat(),
        }

        self.db.commit()
        self.db.refresh(refund_transaction)

        # TODO: Thực hiện logic hoàn tiền thực tế với cổng thanh toán

        return TransactionResponse.model_validate(refund_transaction)
