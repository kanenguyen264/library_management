"""
API quản lý cache cho admin site.

Cung cấp các endpoints để quản lý cache:
- Xem thống kê cache
- Xóa cache theo namespace, pattern, tags
- Thiết lập lịch dọn dẹp cache tự động
"""

from typing import Dict, List, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body, Path
from pydantic import BaseModel, Field

from app.security.access_control.rbac import get_current_super_admin
from app.admin_site.services.cache_manager_service import CacheManagerService


# Định nghĩa schemas
class ClearCacheByPatternRequest(BaseModel):
    """Request body cho việc xóa cache theo pattern."""

    pattern: str = Field(..., description="Pattern để xóa cache")
    namespace: Optional[str] = Field(None, description="Namespace (tùy chọn)")


class ClearCacheByTagsRequest(BaseModel):
    """Request body cho việc xóa cache theo tags."""

    tags: List[str] = Field(..., description="Danh sách tags để xóa cache")


class ScheduledCleanupRequest(BaseModel):
    """Request body cho việc thiết lập lịch dọn dẹp cache tự động."""

    schedule_type: str = Field(..., description="Loại lịch (daily, weekly)")
    namespace: Optional[str] = Field(None, description="Namespace (tùy chọn)")
    patterns: Optional[List[str]] = Field(
        None, description="Danh sách patterns (tùy chọn)"
    )
    tags: Optional[List[str]] = Field(None, description="Danh sách tags (tùy chọn)")
    hour: int = Field(0, ge=0, le=23, description="Giờ (0-23)")
    minute: int = Field(0, ge=0, le=59, description="Phút (0-59)")
    day_of_week: int = Field(
        0, ge=0, le=6, description="Ngày trong tuần (0 = Thứ Hai, 6 = Chủ Nhật)"
    )
    enabled: bool = Field(True, description="Bật/tắt lịch")


class ImmediateCleanupRequest(BaseModel):
    """Request body cho việc dọn dẹp cache ngay lập tức."""

    namespace: Optional[str] = Field(None, description="Namespace (tùy chọn)")
    patterns: Optional[List[str]] = Field(
        None, description="Danh sách patterns (tùy chọn)"
    )
    tags: Optional[List[str]] = Field(None, description="Danh sách tags (tùy chọn)")


# Tạo router
router = APIRouter(
    prefix="/cache", tags=["cache"], dependencies=[Depends(get_current_super_admin)]
)


@router.get("/stats", response_model=Dict[str, Any])
async def get_cache_stats():
    """
    Lấy thống kê về cache.
    Chỉ Super Admin mới có quyền truy cập.
    """
    service = CacheManagerService()
    return await service.get_cache_stats()


@router.delete("/namespaces/{namespace}", response_model=Dict[str, Any])
async def clear_namespace(namespace: str = Path(..., description="Namespace cần xóa")):
    """
    Xóa toàn bộ cache trong namespace.
    Chỉ Super Admin mới có quyền truy cập.
    """
    service = CacheManagerService()
    return await service.clear_namespace(namespace)


@router.post("/pattern", response_model=Dict[str, Any])
async def clear_by_pattern(request: ClearCacheByPatternRequest):
    """
    Xóa cache theo pattern.
    Chỉ Super Admin mới có quyền truy cập.
    """
    service = CacheManagerService()
    return await service.clear_pattern(request.pattern, request.namespace)


@router.post("/tags", response_model=Dict[str, Any])
async def clear_by_tags(request: ClearCacheByTagsRequest):
    """
    Xóa cache theo tags.
    Chỉ Super Admin mới có quyền truy cập.
    """
    service = CacheManagerService()
    return await service.clear_tags(request.tags)


@router.post("/schedule", response_model=Dict[str, Any])
async def setup_scheduled_cleanup(request: ScheduledCleanupRequest):
    """
    Thiết lập lịch dọn dẹp cache tự động.
    Chỉ Super Admin mới có quyền truy cập.
    """
    service = CacheManagerService()
    return await service.setup_scheduled_cleanup(
        schedule_type=request.schedule_type,
        namespace=request.namespace,
        patterns=request.patterns,
        tags=request.tags,
        hour=request.hour,
        minute=request.minute,
        day_of_week=request.day_of_week,
        enabled=request.enabled,
    )


@router.post("/cleanup", response_model=Dict[str, Any])
async def run_immediate_cleanup(request: ImmediateCleanupRequest):
    """
    Chạy ngay lập tức việc dọn dẹp cache.
    Chỉ Super Admin mới có quyền truy cập.
    """
    service = CacheManagerService()
    return await service.run_immediate_cleanup(
        namespace=request.namespace, patterns=request.patterns, tags=request.tags
    )
