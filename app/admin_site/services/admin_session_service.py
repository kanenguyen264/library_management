from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from app.admin_site.models import AdminSession
from app.admin_site.schemas.admin_session import AdminSessionCreate
from app.admin_site.repositories.admin_session_repo import AdminSessionRepository
from app.logging.setup import get_logger
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate
from app.security.jwt import decode_token

logger = get_logger(__name__)


def get_admin_sessions(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    admin_id: Optional[int] = None,
    status: Optional[str] = None,
    ip_address: Optional[str] = None,
    order_by: str = "login_time",
    order_desc: bool = True,
    viewer_admin_id: Optional[int] = None,
) -> List[AdminSession]:
    """
    Lấy danh sách phiên đăng nhập admin.

    Args:
        db: Database session
        skip: Số lượng bản ghi bỏ qua
        limit: Số lượng bản ghi tối đa
        admin_id: ID admin để lọc
        status: Trạng thái phiên (active/inactive)
        ip_address: Địa chỉ IP để lọc
        order_by: Trường sắp xếp
        order_desc: Sắp xếp giảm dần nếu True
        viewer_admin_id: ID của admin thực hiện hành động xem

    Returns:
        Danh sách phiên đăng nhập
    """
    try:
        sessions = AdminSessionRepository.get_all(
            db, skip, limit, admin_id, status, ip_address, order_by, order_desc
        )

        # Log admin activity
        if viewer_admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=viewer_admin_id,
                        activity_type="VIEW",
                        entity_type="ADMIN_SESSION",
                        entity_id=0,
                        description="Viewed admin sessions list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "filtered_admin_id": admin_id,
                            "status": status,
                            "ip_address": ip_address,
                            "order_by": order_by,
                            "order_desc": order_desc,
                            "results_count": len(sessions),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return sessions
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách phiên đăng nhập: {str(e)}")
        raise e


def get_admin_session_by_id(
    db: Session, session_id: int, admin_id: Optional[int] = None
) -> Optional[AdminSession]:
    """
    Lấy thông tin phiên đăng nhập theo ID.

    Args:
        db: Database session
        session_id: ID phiên đăng nhập
        admin_id: ID của admin thực hiện hành động

    Returns:
        AdminSession object nếu tìm thấy, None nếu không
    """
    try:
        session = AdminSessionRepository.get_by_id(db, session_id)

        # Log admin activity
        if admin_id and session:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="ADMIN_SESSION",
                        entity_id=session_id,
                        description=f"Viewed admin session details - ID: {session_id}",
                        metadata={
                            "session_id": session_id,
                            "session_admin_id": session.admin_id,
                            "ip_address": session.ip_address,
                            "status": session.status,
                            "login_time": (
                                session.login_time.isoformat()
                                if session.login_time
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return session
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin phiên đăng nhập theo ID: {str(e)}")
        return None


def get_admin_session_by_token(
    db: Session, token: str, admin_id: Optional[int] = None
) -> Optional[AdminSession]:
    """
    Lấy thông tin phiên đăng nhập theo token.

    Args:
        db: Database session
        token: Token phiên đăng nhập
        admin_id: ID của admin thực hiện hành động

    Returns:
        AdminSession object nếu tìm thấy, None nếu không
    """
    try:
        session = AdminSessionRepository.get_by_token(db, token, active_only=True)

        # Log admin activity - only log if it's an admin checking the token, not during normal auth operations
        if admin_id and session and admin_id != session.admin_id:
            try:
                # For security, we don't log the actual token
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="ADMIN_SESSION",
                        entity_id=session.id,
                        description=f"Verified admin session token",
                        metadata={
                            "session_id": session.id,
                            "session_admin_id": session.admin_id,
                            "ip_address": session.ip_address,
                            "status": session.status,
                            "login_time": (
                                session.login_time.isoformat()
                                if session.login_time
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return session
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin phiên đăng nhập theo token: {str(e)}")
        return None


def create_admin_session(
    db: Session, admin_id: int, ip_address: str, user_agent: str, token: str
) -> AdminSession:
    """
    Tạo phiên đăng nhập mới cho admin.

    Args:
        db: Database session
        admin_id: ID admin
        ip_address: Địa chỉ IP của client
        user_agent: User agent của client
        token: Token phiên đăng nhập

    Returns:
        AdminSession object đã tạo
    """
    try:
        session_data = {
            "admin_id": admin_id,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "token": token,
            "status": "active",
            "login_time": datetime.now(timezone.utc),
        }

        session = AdminSessionRepository.create(db, session_data)

        # Log admin activity - this is logged in auth_service.py when admin logs in

        return session
    except Exception as e:
        logger.error(f"Lỗi khi tạo phiên đăng nhập: {str(e)}")
        raise e


def invalidate_session(db: Session, token: str, admin_id: Optional[int] = None) -> bool:
    """
    Vô hiệu hóa phiên đăng nhập (đăng xuất).

    Args:
        db: Database session
        token: Token phiên đăng nhập
        admin_id: ID của admin thực hiện hành động (có thể khác với admin_id của phiên)

    Returns:
        True nếu thành công, False nếu thất bại
    """
    try:
        # Get session before invalidating to log information
        session = AdminSessionRepository.get_by_token(db, token)

        result = AdminSessionRepository.invalidate(db, token)

        # Log admin activity
        if admin_id and session:
            try:
                # Check if admin is invalidating their own session or someone else's
                session_owner = session.admin_id
                action_type = (
                    "self_logout" if session_owner == admin_id else "forced_logout"
                )

                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="ADMIN_SESSION",
                        entity_id=session.id,
                        description=f"{'Logged out' if action_type == 'self_logout' else 'Forced logout for admin ID: ' + str(session_owner)}",
                        metadata={
                            "action_type": action_type,
                            "session_id": session.id,
                            "session_admin_id": session_owner,
                            "ip_address": session.ip_address,
                            "login_time": (
                                session.login_time.isoformat()
                                if session.login_time
                                else None
                            ),
                            "logout_time": datetime.now(timezone.utc).isoformat(),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return result
    except Exception as e:
        logger.error(f"Lỗi khi vô hiệu hóa phiên đăng nhập: {str(e)}")
        raise e


def invalidate_all_admin_sessions(
    db: Session, admin_id: int, actor_admin_id: Optional[int] = None
) -> int:
    """
    Vô hiệu hóa tất cả phiên đăng nhập của admin.

    Args:
        db: Database session
        admin_id: ID admin có phiên cần vô hiệu hóa
        actor_admin_id: ID của admin thực hiện hành động

    Returns:
        Số phiên đăng nhập đã vô hiệu hóa
    """
    try:
        count = AdminSessionRepository.invalidate_all_by_admin(db, admin_id)

        # Log admin activity
        if actor_admin_id:
            try:
                # Check if admin is invalidating their own sessions or someone else's
                action_type = (
                    "self_logout_all"
                    if admin_id == actor_admin_id
                    else "forced_logout_all"
                )

                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=actor_admin_id,
                        activity_type="UPDATE",
                        entity_type="ADMIN_SESSION",
                        entity_id=0,
                        description=f"{'Logged out from all sessions' if action_type == 'self_logout_all' else 'Forced logout for all sessions of admin ID: ' + str(admin_id)}",
                        metadata={
                            "action_type": action_type,
                            "target_admin_id": admin_id,
                            "sessions_count": count,
                            "logout_time": datetime.now(timezone.utc).isoformat(),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return count
    except Exception as e:
        logger.error(f"Lỗi khi vô hiệu hóa tất cả phiên đăng nhập: {str(e)}")
        raise e


def clean_expired_sessions(
    db: Session, days: int = 30, admin_id: Optional[int] = None
) -> int:
    """
    Xóa các phiên đăng nhập đã hết hạn.

    Args:
        db: Database session
        days: Số ngày trước khi xem là hết hạn
        admin_id: ID của admin thực hiện hành động

    Returns:
        Số phiên đăng nhập đã xóa
    """
    try:
        count = AdminSessionRepository.clean_expired(db, days)

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="ADMIN_SESSION",
                        entity_id=0,
                        description=f"Cleaned expired admin sessions (older than {days} days)",
                        metadata={
                            "days_threshold": days,
                            "deleted_sessions_count": count,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return count
    except Exception as e:
        logger.error(f"Lỗi khi xóa phiên đăng nhập hết hạn: {str(e)}")
        raise e


def validate_refresh_token(db: Session, token: str) -> Optional[Dict[str, Any]]:
    """
    Xác thực refresh token và kiểm tra xem phiên đăng nhập có còn hợp lệ không.

    Args:
        db: Database session
        token: Refresh token cần xác thực

    Returns:
        Dict thông tin từ token nếu token hợp lệ, None nếu không
    """
    try:
        # Kiểm tra xem token có tồn tại trong database không
        session = AdminSessionRepository.get_by_token(db, token, active_only=True)
        if not session:
            logger.warning(f"Không tìm thấy phiên đăng nhập với token: {token[:10]}...")
            return None

        # Giải mã token để lấy thông tin
        from app.core.exceptions import TokenExpired, InvalidToken

        try:
            payload = decode_token(token)

            # Kiểm tra token type
            if payload.get("type") != "refresh":
                logger.warning(f"Token không phải là refresh token: {token[:10]}...")
                return None

            return payload
        except TokenExpired:
            logger.warning(f"Refresh token đã hết hạn: {token[:10]}...")
            # Vô hiệu hóa phiên đăng nhập nếu token đã hết hạn
            AdminSessionRepository.invalidate(db, token)
            return None
        except InvalidToken:
            logger.warning(f"Refresh token không hợp lệ: {token[:10]}...")
            return None
        except Exception as e:
            logger.error(f"Lỗi khi giải mã refresh token: {str(e)}")
            return None

    except Exception as e:
        logger.error(f"Lỗi khi xác thực refresh token: {str(e)}")
        return None


def invalidate_session_by_refresh_token(db: Session, refresh_token: str) -> bool:
    """
    Vô hiệu hóa phiên đăng nhập bằng refresh token.

    Args:
        db: Database session
        refresh_token: Refresh token của phiên đăng nhập

    Returns:
        True nếu thành công, False nếu thất bại
    """
    try:
        # Kiểm tra xem token có tồn tại trong database không
        session = AdminSessionRepository.get_by_token(db, refresh_token)
        if not session:
            logger.warning(
                f"Không tìm thấy phiên đăng nhập với token: {refresh_token[:10]}..."
            )
            return False

        # Vô hiệu hóa phiên đăng nhập
        return AdminSessionRepository.invalidate(db, refresh_token)
    except Exception as e:
        logger.error(
            f"Lỗi khi vô hiệu hóa phiên đăng nhập bằng refresh token: {str(e)}"
        )
        return False
