"""
Module cấu hình scaling.

Module này export các cấu hình liên quan đến việc mở rộng quy mô ứng dụng:
- Autoscaling: Cấu hình tự động mở rộng
"""

from config.scaling.autoscaling import AutoscalingConfig

__all__ = ["AutoscalingConfig"]
