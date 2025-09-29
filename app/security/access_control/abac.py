from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable, Union
from fastapi import HTTPException, Depends, status
from sqlalchemy.orm import Session
from app.core.db import get_session
from app.security.access_control.rbac import get_current_user, get_current_admin
from functools import wraps


class Policy:
    """
    Lớp cơ sở cho Attribute-Based Access Control policies.
    ABAC cho phép kiểm soát truy cập dựa vào nhiều thuộc tính như:
    - Thuộc tính người dùng (role, department, subscription)
    - Thuộc tính tài nguyên (owner, status, type)
    - Thuộc tính môi trường (time, location, device)
    - Thuộc tính hành động (read, write, delete)
    """

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description

    def evaluate(
        self,
        user: Any,
        resource: Any = None,
        action: str = None,
        context: Dict[str, Any] = None,
    ) -> bool:
        """
        Đánh giá policy cho user, resource và action cụ thể.

        Args:
            user: User object
            resource: Resource object
            action: Action being performed
            context: Additional context variables

        Returns:
            True if allowed, False if denied
        """
        raise NotImplementedError("Subclasses must implement evaluate()")


class OwnershipPolicy(Policy):
    """
    Policy cho phép truy cập nếu user là chủ sở hữu resource.
    """

    def __init__(
        self,
        name: str = "ownership",
        description: str = "Allow access if user is the owner of the resource",
        user_id_field: str = "id",
        resource_owner_field: str = "user_id",
        owner_id_field: str = "owner_id",
    ):
        super().__init__(name, description)
        self.user_id_field = user_id_field
        self.resource_owner_field = resource_owner_field
        self.owner_id_field = owner_id_field

    def evaluate(
        self,
        user: Any,
        resource: Any = None,
        action: str = None,
        context: Dict[str, Any] = None,
    ) -> bool:
        """
        Kiểm tra xem user có phải là chủ sở hữu của resource hay không.

        Args:
            user: User object
            resource: Resource object
            action: Action being performed
            context: Additional context variables

        Returns:
            True if user is the owner, False otherwise
        """
        if not resource:
            return False

        user_id = getattr(user, self.user_id_field)

        # Kiểm tra các trường khác nhau có thể chứa thông tin chủ sở hữu
        if hasattr(resource, self.resource_owner_field):
            return getattr(resource, self.resource_owner_field) == user_id

        if hasattr(resource, self.owner_id_field):
            return getattr(resource, self.owner_id_field) == user_id

        return False


class SubscriptionPolicy(Policy):
    """
    Policy cho phép truy cập dựa trên gói đăng ký của user.
    """

    def __init__(
        self,
        name: str = "subscription",
        description: str = "Allow access based on user's subscription level",
        allowed_plans: List[str] = None,
    ):
        super().__init__(name, description)
        self.allowed_plans = allowed_plans or ["premium", "enterprise"]

    def evaluate(
        self,
        user: Any,
        resource: Any = None,
        action: str = None,
        context: Dict[str, Any] = None,
    ) -> bool:
        """
        Kiểm tra xem user có gói đăng ký phù hợp không.

        Args:
            user: User object
            resource: Resource object
            action: Action being performed
            context: Additional context variables

        Returns:
            True if user has an allowed subscription plan, False otherwise
        """
        # Kiểm tra user có thuộc tính subscription không
        if not hasattr(user, "subscription") or not user.subscription:
            return False

        # Kiểm tra subscription có thuộc tính plan không
        if not hasattr(user.subscription, "plan") or not user.subscription.plan:
            return False

        return user.subscription.plan in self.allowed_plans


class TimeWindowPolicy(Policy):
    """
    Policy cho phép truy cập trong khung giờ nhất định.
    """

    def __init__(
        self,
        name: str = "time_window",
        description: str = "Allow access during specific time windows",
        start_hour: int = 8,
        end_hour: int = 20,
        allowed_days: List[int] = None,  # 0 = Monday, 6 = Sunday
    ):
        super().__init__(name, description)
        self.start_hour = start_hour
        self.end_hour = end_hour
        self.allowed_days = allowed_days or list(range(7))  # Default all days

    def evaluate(
        self,
        user: Any,
        resource: Any = None,
        action: str = None,
        context: Dict[str, Any] = None,
    ) -> bool:
        """
        Kiểm tra xem thời gian hiện tại có trong khung thời gian cho phép không.

        Args:
            user: User object
            resource: Resource object
            action: Action being performed
            context: Additional context variables

        Returns:
            True if current time is within allowed window, False otherwise
        """
        now = datetime.datetime.now()
        current_hour = now.hour
        current_day = now.weekday()  # 0 = Monday, 6 = Sunday

        # Kiểm tra xem ngày hiện tại có trong danh sách ngày cho phép không
        if current_day not in self.allowed_days:
            return False

        # Kiểm tra xem giờ hiện tại có trong khung giờ cho phép không
        return self.start_hour <= current_hour < self.end_hour


class CompositePolicy(Policy):
    """
    Policy kết hợp nhiều policy con với điều kiện AND hoặc OR.
    """

    def __init__(
        self,
        name: str,
        policies: List[Policy],
        operator: str = "AND",
        description: str = "",
    ):
        super().__init__(name, description)
        self.policies = policies
        self.operator = operator.upper()

        if self.operator not in ["AND", "OR"]:
            raise ValueError("Operator must be either 'AND' or 'OR'")

    def evaluate(
        self,
        user: Any,
        resource: Any = None,
        action: str = None,
        context: Dict[str, Any] = None,
    ) -> bool:
        """
        Đánh giá tất cả các policy con và kết hợp kết quả.

        Args:
            user: User object
            resource: Resource object
            action: Action being performed
            context: Additional context variables

        Returns:
            Combined result based on operator
        """
        if not self.policies:
            return False

        if self.operator == "AND":
            return all(
                policy.evaluate(user, resource, action, context)
                for policy in self.policies
            )
        else:  # OR
            return any(
                policy.evaluate(user, resource, action, context)
                for policy in self.policies
            )


def check_policy(
    policy: Union[Policy, List[Policy]],
    resource_getter: Optional[Callable] = None,
    action: Optional[str] = None,
):
    """
    Decorator để kiểm tra policy cho endpoint API.

    Args:
        policy: Policy hoặc list các Policy để kiểm tra
        resource_getter: Function để lấy resource từ request params
        action: Hành động đang thực hiện

    Returns:
        Decorator function
    """
    # Convert single policy to list
    policies = policy if isinstance(policy, list) else [policy]

    def policy_decorator(
        current_user=Depends(get_current_user), db: Session = Depends(get_session)
    ):
        # Context chung cho các policy
        context = {"db": db, "timestamp": datetime.datetime.now()}

        # Lấy resource nếu có resource_getter
        resource = None
        if resource_getter:
            try:
                resource = resource_getter(db=db)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Resource not found: {str(e)}",
                )

        # Đánh giá tất cả policy
        for p in policies:
            if not p.evaluate(current_user, resource, action, context):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Policy check failed: {p.name}",
                )

        return current_user

    return policy_decorator
