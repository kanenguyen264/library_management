from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.admin_site.models import Role, RolePermission, Permission, AdminRole
from app.logging.setup import get_logger

logger = get_logger(__name__)

class RoleRepository:
    """
    Repository để thao tác với Role trong cơ sở dữ liệu.
    """
    
    @staticmethod
    def get_by_id(db: Session, role_id: int) -> Optional[Role]:
        """
        Lấy vai trò theo ID.
        
        Args:
            db: Database session
            role_id: ID của vai trò
            
        Returns:
            Role object nếu tìm thấy, None nếu không
        """
        return db.query(Role).filter(Role.id == role_id).first()
    
    @staticmethod
    def get_by_name(db: Session, name: str) -> Optional[Role]:
        """
        Lấy vai trò theo tên.
        
        Args:
            db: Database session
            name: Tên của vai trò
            
        Returns:
            Role object nếu tìm thấy, None nếu không
        """
        return db.query(Role).filter(Role.name == name).first()
    
    @staticmethod
    def count(
        db: Session, 
        search: Optional[str] = None
    ) -> int:
        """
        Đếm số lượng vai trò với các điều kiện lọc.
        """
        query = db.query(func.count(Role.id))
        
        if search:
            query = query.filter(
                or_(
                    Role.name.ilike(f"%{search}%"),
                    Role.description.ilike(f"%{search}%")
                )
            )
        
        return query.scalar()
    
    @staticmethod
    def get_all(
        db: Session, 
        skip: int = 0, 
        limit: int = 100,
        search: Optional[str] = None,
        order_by: str = "name",
        order_desc: bool = False
    ) -> List[Role]:
        """
        Lấy danh sách vai trò với các tùy chọn lọc.
        
        Args:
            db: Database session
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa
            search: Tìm kiếm theo tên, mô tả
            
        Returns:
            Danh sách vai trò
        """
        query = db.query(Role)
        
        if search:
            query = query.filter(
                or_(
                    Role.name.ilike(f"%{search}%"),
                    Role.description.ilike(f"%{search}%")
                )
            )
        
        # Xử lý sắp xếp
        if hasattr(Role, order_by):
            if order_desc:
                query = query.order_by(desc(getattr(Role, order_by)))
            else:
                query = query.order_by(getattr(Role, order_by))
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def get_by_conditions(
        db: Session,
        conditions: Dict[str, Any],
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        order_desc: bool = False
    ) -> List[Role]:
        """
        Lấy danh sách vai trò theo các điều kiện tùy chỉnh.
        """
        query = db.query(Role)
        
        for field, value in conditions.items():
            if value is not None:
                if field == 'search':
                    query = query.filter(
                        or_(
                            Role.name.ilike(f"%{value}%"),
                            Role.description.ilike(f"%{value}%")
                        )
                    )
                elif hasattr(Role, field):
                    query = query.filter(getattr(Role, field) == value)
        
        if order_by and hasattr(Role, order_by):
            if order_desc:
                query = query.order_by(desc(getattr(Role, order_by)))
            else:
                query = query.order_by(getattr(Role, order_by))
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def create(db: Session, role_data: Dict[str, Any]) -> Role:
        """
        Tạo vai trò mới.
        
        Args:
            db: Database session
            role_data: Dữ liệu vai trò cần tạo
            
        Returns:
            Role object đã tạo
        """
        try:
            db_role = Role(**role_data)
            db.add(db_role)
            db.commit()
            db.refresh(db_role)
            logger.info(f"Đã tạo vai trò mới: {db_role.name}")
            return db_role
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi tạo vai trò: {str(e)}")
            raise e
    
    @staticmethod
    def update(db: Session, role_id: int, role_data: Dict[str, Any]) -> Optional[Role]:
        """
        Cập nhật thông tin vai trò.
        
        Args:
            db: Database session
            role_id: ID của vai trò
            role_data: Dữ liệu cập nhật
            
        Returns:
            Role object đã cập nhật hoặc None nếu không tìm thấy
        """
        try:
            db_role = RoleRepository.get_by_id(db, role_id)
            if not db_role:
                logger.warning(f"Không tìm thấy vai trò ID={role_id} để cập nhật")
                return None
            
            for key, value in role_data.items():
                setattr(db_role, key, value)
            
            db_role.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_role)
            logger.info(f"Đã cập nhật vai trò ID={role_id}")
            return db_role
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi cập nhật vai trò ID={role_id}: {str(e)}")
            raise e
    
    @staticmethod
    def delete(db: Session, role_id: int) -> bool:
        """
        Xóa vai trò.
        
        Args:
            db: Database session
            role_id: ID của vai trò
            
        Returns:
            True nếu xóa thành công, False nếu không
        """
        try:
            db_role = RoleRepository.get_by_id(db, role_id)
            if not db_role:
                logger.warning(f"Không tìm thấy vai trò ID={role_id} để xóa")
                return False
            
            # Xóa tất cả các quyền liên quan
            db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
            
            # Xóa tất cả liên kết với admin
            db.query(AdminRole).filter(AdminRole.role_id == role_id).delete()
            
            # Xóa vai trò
            db.delete(db_role)
            db.commit()
            logger.info(f"Đã xóa vai trò ID={role_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi xóa vai trò ID={role_id}: {str(e)}")
            raise e
    
    @staticmethod
    def get_permissions(db: Session, role_id: int) -> List[Permission]:
        """
        Lấy danh sách quyền của vai trò.
        
        Args:
            db: Database session
            role_id: ID của vai trò
            
        Returns:
            Danh sách quyền
        """
        try:
            return (
                db.query(Permission)
                .join(RolePermission, Permission.id == RolePermission.permission_id)
                .filter(RolePermission.role_id == role_id)
                .all()
            )
        except Exception as e:
            logger.error(f"Lỗi khi lấy danh sách quyền của vai trò ID={role_id}: {str(e)}")
            raise e
    
    @staticmethod
    def add_permission(db: Session, role_id: int, permission_id: int) -> bool:
        """
        Thêm quyền cho vai trò.
        
        Args:
            db: Database session
            role_id: ID của vai trò
            permission_id: ID của quyền
            
        Returns:
            True nếu thêm thành công, False nếu không
        """
        try:
            # Kiểm tra xem vai trò và quyền có tồn tại không
            role = RoleRepository.get_by_id(db, role_id)
            if not role:
                logger.warning(f"Không tìm thấy vai trò ID={role_id} để thêm quyền")
                return False
                
            permission = db.query(Permission).filter(Permission.id == permission_id).first()
            if not permission:
                logger.warning(f"Không tìm thấy quyền ID={permission_id} để thêm vào vai trò")
                return False
                
            # Kiểm tra xem đã có quyền này trong vai trò chưa
            existing = (
                db.query(RolePermission)
                .filter(
                    RolePermission.role_id == role_id,
                    RolePermission.permission_id == permission_id
                )
                .first()
            )
            
            if existing:
                logger.info(f"Quyền ID={permission_id} đã tồn tại trong vai trò ID={role_id}")
                return True
                
            # Thêm quyền mới
            role_permission = RolePermission(
                role_id=role_id,
                permission_id=permission_id,
                created_at=datetime.now(timezone.utc)
            )
            db.add(role_permission)
            db.commit()
            logger.info(f"Đã thêm quyền ID={permission_id} vào vai trò ID={role_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi thêm quyền ID={permission_id} vào vai trò ID={role_id}: {str(e)}")
            raise e
    
    @staticmethod
    def remove_permission(db: Session, role_id: int, permission_id: int) -> bool:
        """
        Xóa quyền khỏi vai trò.
        
        Args:
            db: Database session
            role_id: ID của vai trò
            permission_id: ID của quyền
            
        Returns:
            True nếu xóa thành công, False nếu không
        """
        try:
            deleted = (
                db.query(RolePermission)
                .filter(
                    RolePermission.role_id == role_id,
                    RolePermission.permission_id == permission_id
                )
                .delete()
            )
            db.commit()
            if deleted > 0:
                logger.info(f"Đã xóa quyền ID={permission_id} khỏi vai trò ID={role_id}")
            else:
                logger.info(f"Không tìm thấy quyền ID={permission_id} trong vai trò ID={role_id} để xóa")
            return deleted > 0
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi xóa quyền ID={permission_id} khỏi vai trò ID={role_id}: {str(e)}")
            raise e
