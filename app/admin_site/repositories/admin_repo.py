from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.admin_site.models import Admin, Role, Permission, AdminRole
from app.logging.setup import get_logger

logger = get_logger(__name__)

class AdminRepository:
    """
    Repository để thao tác với Admin trong cơ sở dữ liệu.
    """
    
    @staticmethod
    def get_by_id(db: Session, admin_id: int) -> Optional[Admin]:
        """
        Lấy admin theo ID.
        
        Args:
            db: Database session
            admin_id: ID của admin
            
        Returns:
            Admin object nếu tìm thấy, None nếu không
        """
        return db.query(Admin).filter(Admin.id == admin_id).first()
    
    @staticmethod
    def get_by_username(db: Session, username: str) -> Optional[Admin]:
        """
        Lấy admin theo username.
        
        Args:
            db: Database session
            username: Username của admin
            
        Returns:
            Admin object nếu tìm thấy, None nếu không
        """
        return db.query(Admin).filter(Admin.username == username).first()
    
    @staticmethod
    def get_by_email(db: Session, email: str) -> Optional[Admin]:
        """
        Lấy admin theo email.
        
        Args:
            db: Database session
            email: Email của admin
            
        Returns:
            Admin object nếu tìm thấy, None nếu không
        """
        return db.query(Admin).filter(Admin.email == email).first()
    
    @staticmethod
    def count(
        db: Session, 
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_super_admin: Optional[bool] = None
    ) -> int:
        """
        Đếm số lượng admin với các điều kiện lọc.
        """
        query = db.query(func.count(Admin.id))
        
        if search:
            query = query.filter(
                or_(
                    Admin.username.ilike(f"%{search}%"),
                    Admin.email.ilike(f"%{search}%"),
                    Admin.full_name.ilike(f"%{search}%")
                )
            )
        
        if is_active is not None:
            query = query.filter(Admin.is_active == is_active)
            
        if is_super_admin is not None:
            query = query.filter(Admin.is_super_admin == is_super_admin)
        
        return query.scalar()
    
    @staticmethod
    def get_all(
        db: Session, 
        skip: int = 0, 
        limit: int = 100,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_super_admin: Optional[bool] = None,
        order_by: str = "id",
        order_desc: bool = False
    ) -> List[Admin]:
        """
        Lấy danh sách admin với các tùy chọn lọc.
        
        Args:
            db: Database session
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa
            search: Tìm kiếm theo tên, username, email
            is_active: Lọc theo trạng thái kích hoạt
            is_super_admin: Lọc theo trạng thái là super admin
            
        Returns:
            Danh sách admin
        """
        query = db.query(Admin)
        
        if search:
            query = query.filter(
                or_(
                    Admin.username.ilike(f"%{search}%"),
                    Admin.email.ilike(f"%{search}%"),
                    Admin.full_name.ilike(f"%{search}%")
                )
            )
        
        if is_active is not None:
            query = query.filter(Admin.is_active == is_active)
        
        if is_super_admin is not None:
            query = query.filter(Admin.is_super_admin == is_super_admin)
        
        # Xử lý sắp xếp
        if hasattr(Admin, order_by):
            if order_desc:
                query = query.order_by(desc(getattr(Admin, order_by)))
            else:
                query = query.order_by(getattr(Admin, order_by))
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def get_by_conditions(
        db: Session,
        conditions: Dict[str, Any],
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        order_desc: bool = False
    ) -> List[Admin]:
        """
        Lấy danh sách admin theo các điều kiện tùy chỉnh.
        """
        query = db.query(Admin)
        
        for field, value in conditions.items():
            if value is not None:
                if field == 'search':
                    query = query.filter(
                        or_(
                            Admin.username.ilike(f"%{value}%"),
                            Admin.email.ilike(f"%{value}%"),
                            Admin.full_name.ilike(f"%{value}%")
                        )
                    )
                elif hasattr(Admin, field):
                    query = query.filter(getattr(Admin, field) == value)
        
        if order_by and hasattr(Admin, order_by):
            if order_desc:
                query = query.order_by(desc(getattr(Admin, order_by)))
            else:
                query = query.order_by(getattr(Admin, order_by))
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def create(db: Session, admin_data: Dict[str, Any]) -> Admin:
        """
        Tạo admin mới.
        
        Args:
            db: Database session
            admin_data: Dữ liệu admin cần tạo
            
        Returns:
            Admin object đã tạo
        """
        try:
            db_admin = Admin(**admin_data)
            db.add(db_admin)
            db.commit()
            db.refresh(db_admin)
            logger.info(f"Đã tạo admin mới: {db_admin.username}")
            return db_admin
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi tạo admin: {str(e)}")
            raise e
    
    @staticmethod
    def update(db: Session, admin_id: int, admin_data: Dict[str, Any]) -> Optional[Admin]:
        """
        Cập nhật thông tin admin.
        
        Args:
            db: Database session
            admin_id: ID của admin
            admin_data: Dữ liệu cập nhật
            
        Returns:
            Admin object đã cập nhật hoặc None nếu không tìm thấy
        """
        try:
            db_admin = AdminRepository.get_by_id(db, admin_id)
            if not db_admin:
                logger.warning(f"Không tìm thấy admin ID={admin_id} để cập nhật")
                return None
            
            for key, value in admin_data.items():
                setattr(db_admin, key, value)
            
            db_admin.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_admin)
            logger.info(f"Đã cập nhật admin ID={admin_id}")
            return db_admin
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi cập nhật admin ID={admin_id}: {str(e)}")
            raise e
    
    @staticmethod
    def update_password(db: Session, admin_id: int, hashed_password: str) -> Optional[Admin]:
        """
        Cập nhật mật khẩu admin.
        """
        try:
            db_admin = AdminRepository.get_by_id(db, admin_id)
            if not db_admin:
                logger.warning(f"Không tìm thấy admin ID={admin_id} để cập nhật mật khẩu")
                return None
            
            db_admin.password_hash = hashed_password
            db_admin.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_admin)
            logger.info(f"Đã cập nhật mật khẩu cho admin ID={admin_id}")
            return db_admin
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi cập nhật mật khẩu admin ID={admin_id}: {str(e)}")
            raise e
    
    @staticmethod
    def update_last_login(db: Session, admin_id: int) -> Optional[Admin]:
        """
        Cập nhật thời gian đăng nhập cuối.
        """
        try:
            db_admin = AdminRepository.get_by_id(db, admin_id)
            if not db_admin:
                logger.warning(f"Không tìm thấy admin ID={admin_id} để cập nhật thời gian đăng nhập")
                return None
            
            db_admin.last_login = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_admin)
            return db_admin
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi cập nhật thời gian đăng nhập admin ID={admin_id}: {str(e)}")
            raise e
    
    @staticmethod
    def delete(db: Session, admin_id: int) -> bool:
        """
        Xóa admin.
        
        Args:
            db: Database session
            admin_id: ID của admin
            
        Returns:
            True nếu xóa thành công, False nếu không
        """
        try:
            db_admin = AdminRepository.get_by_id(db, admin_id)
            if not db_admin:
                logger.warning(f"Không tìm thấy admin ID={admin_id} để xóa")
                return False
            
            db.delete(db_admin)
            db.commit()
            logger.info(f"Đã xóa admin ID={admin_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi xóa admin ID={admin_id}: {str(e)}")
            raise e
    
    @staticmethod
    def get_roles(db: Session, admin_id: int) -> List[Role]:
        """
        Lấy danh sách vai trò của admin.
        
        Args:
            db: Database session
            admin_id: ID của admin
            
        Returns:
            Danh sách vai trò
        """
        try:
            return (
                db.query(Role)
                .join(AdminRole, Role.id == AdminRole.role_id)
                .filter(AdminRole.admin_id == admin_id)
                .all()
            )
        except Exception as e:
            logger.error(f"Lỗi khi lấy danh sách vai trò của admin ID={admin_id}: {str(e)}")
            raise e
    
    @staticmethod
    def get_permissions(db: Session, admin_id: int) -> List[Permission]:
        """
        Lấy danh sách quyền của admin.
        
        Args:
            db: Database session
            admin_id: ID của admin
            
        Returns:
            Danh sách quyền
        """
        try:
            return (
                db.query(Permission)
                .join(AdminRole, AdminRole.admin_id == admin_id)
                .join(Permission, Permission.id == AdminRole.role_id)
                .all()
            )
        except Exception as e:
            logger.error(f"Lỗi khi lấy danh sách quyền của admin ID={admin_id}: {str(e)}")
            raise e
    
    @staticmethod
    def has_permission(db: Session, admin_id: int, permission_name: str) -> bool:
        """
        Kiểm tra xem admin có quyền cụ thể không.
        
        Args:
            db: Database session
            admin_id: ID của admin
            permission_name: Tên quyền cần kiểm tra
            
        Returns:
            True nếu có quyền, False nếu không
        """
        try:
            db_admin = AdminRepository.get_by_id(db, admin_id)
            if not db_admin:
                logger.warning(f"Không tìm thấy admin ID={admin_id} để kiểm tra quyền")
                return False
                
            if db_admin.is_super_admin:
                return True
                
            permission_count = (
                db.query(func.count(Permission.id))
                .join(AdminRole, AdminRole.admin_id == admin_id)
                .join(Permission, Permission.id == AdminRole.role_id)
                .filter(Permission.name == permission_name)
                .scalar()
            )
            
            return permission_count > 0
        except Exception as e:
            logger.error(f"Lỗi khi kiểm tra quyền của admin ID={admin_id}: {str(e)}")
            return False
