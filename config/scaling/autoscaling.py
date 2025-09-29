"""
Cấu hình Autoscaling.

Module này định nghĩa các cấu hình tự động mở rộng cho ứng dụng:
- Cấu hình mở rộng worker
- Cấu hình mở rộng dựa trên CPU, memory, request rate
- Giá trị ngưỡng kích hoạt mở rộng
- Giá trị tối đa và tối thiểu
"""

from typing import Dict, List, Optional, Union, Literal
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AutoscalingConfig(BaseSettings):
    """
    Cấu hình tự động mở rộng quy mô.

    Attributes:
        AUTOSCALING_ENABLED: Bật/tắt tính năng tự động mở rộng
        AUTOSCALING_MIN_REPLICAS: Số lượng replicas tối thiểu
        AUTOSCALING_MAX_REPLICAS: Số lượng replicas tối đa
        AUTOSCALING_CPU_THRESHOLD: Ngưỡng CPU để kích hoạt mở rộng (%)
        AUTOSCALING_MEMORY_THRESHOLD: Ngưỡng memory để kích hoạt mở rộng (%)
        AUTOSCALING_REQUEST_THRESHOLD: Ngưỡng request rate để kích hoạt mở rộng (r/s)
        AUTOSCALING_SCALE_UP_COOLDOWN: Thời gian chờ giữa các lần mở rộng (giây)
        AUTOSCALING_SCALE_DOWN_COOLDOWN: Thời gian chờ giữa các lần thu hẹp (giây)
        AUTOSCALING_SCALE_UP_FACTOR: Hệ số mở rộng (%)
        AUTOSCALING_SCALE_DOWN_FACTOR: Hệ số thu hẹp (%)
        AUTOSCALING_STRATEGY: Chiến lược mở rộng
        AUTOSCALING_METRIC_WINDOW: Cửa sổ thời gian để tính toán metrics (giây)
        AUTOSCALING_WORKER_CONCURRENCY: Số lượng worker đồng thời tối đa
        AUTOSCALING_MAX_REQUEST_QUEUE: Kích thước hàng đợi request tối đa
        AUTOSCALING_DB_CONNECTION_PER_WORKER: Số lượng kết nối DB cho mỗi worker
    """

    AUTOSCALING_ENABLED: bool = Field(
        default=False, description="Bật/tắt tính năng tự động mở rộng"
    )

    AUTOSCALING_MIN_REPLICAS: int = Field(
        default=1, description="Số lượng replicas tối thiểu"
    )

    AUTOSCALING_MAX_REPLICAS: int = Field(
        default=10, description="Số lượng replicas tối đa"
    )

    AUTOSCALING_CPU_THRESHOLD: int = Field(
        default=70, description="Ngưỡng CPU để kích hoạt mở rộng (%)"
    )

    AUTOSCALING_MEMORY_THRESHOLD: int = Field(
        default=80, description="Ngưỡng memory để kích hoạt mở rộng (%)"
    )

    AUTOSCALING_REQUEST_THRESHOLD: int = Field(
        default=1000, description="Ngưỡng request rate để kích hoạt mở rộng (r/s)"
    )

    AUTOSCALING_SCALE_UP_COOLDOWN: int = Field(
        default=120, description="Thời gian chờ giữa các lần mở rộng (giây)"
    )

    AUTOSCALING_SCALE_DOWN_COOLDOWN: int = Field(
        default=300, description="Thời gian chờ giữa các lần thu hẹp (giây)"
    )

    AUTOSCALING_SCALE_UP_FACTOR: int = Field(
        default=30, description="Hệ số mở rộng (%)"
    )

    AUTOSCALING_SCALE_DOWN_FACTOR: int = Field(
        default=20, description="Hệ số thu hẹp (%)"
    )

    AUTOSCALING_STRATEGY: Literal["cpu", "memory", "request", "combined"] = Field(
        default="combined", description="Chiến lược mở rộng"
    )

    AUTOSCALING_METRIC_WINDOW: int = Field(
        default=60, description="Cửa sổ thời gian để tính toán metrics (giây)"
    )

    AUTOSCALING_WORKER_CONCURRENCY: int = Field(
        default=4, description="Số lượng worker đồng thời tối đa"
    )

    AUTOSCALING_MAX_REQUEST_QUEUE: int = Field(
        default=100, description="Kích thước hàng đợi request tối đa"
    )

    AUTOSCALING_DB_CONNECTION_PER_WORKER: int = Field(
        default=2, description="Số lượng kết nối DB cho mỗi worker"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_prefix="AUTOSCALING_",
    )

    @validator("AUTOSCALING_MIN_REPLICAS")
    def min_replicas_must_be_positive(cls, v):
        """Validate số lượng replicas tối thiểu."""
        if v < 1:
            raise ValueError("Số lượng replicas tối thiểu phải lớn hơn 0")
        return v

    @validator("AUTOSCALING_MAX_REPLICAS")
    def max_replicas_must_be_greater_than_min(cls, v, values):
        """Validate số lượng replicas tối đa."""
        min_replicas = values.get("AUTOSCALING_MIN_REPLICAS", 1)
        if v < min_replicas:
            raise ValueError(
                "Số lượng replicas tối đa phải lớn hơn hoặc bằng tối thiểu"
            )
        return v

    def calculate_max_db_connections(self) -> int:
        """
        Tính toán số lượng kết nối DB tối đa cần cấu hình.

        Returns:
            Số lượng kết nối DB tối đa
        """
        return (
            self.AUTOSCALING_MAX_REPLICAS
            * self.AUTOSCALING_WORKER_CONCURRENCY
            * self.AUTOSCALING_DB_CONNECTION_PER_WORKER
        )

    def get_worker_settings(self) -> dict:
        """
        Lấy cấu hình worker cho ứng dụng.

        Returns:
            Dict cấu hình worker
        """
        return {
            "workers": self.AUTOSCALING_MIN_REPLICAS
            * self.AUTOSCALING_WORKER_CONCURRENCY,
            "concurrency": self.AUTOSCALING_WORKER_CONCURRENCY,
            "max_requests": self.AUTOSCALING_REQUEST_THRESHOLD,
            "max_requests_jitter": 100,
            "timeout": 120,
        }

    def get_kubernetes_config(self) -> dict:
        """
        Lấy cấu hình Kubernetes HPA.

        Returns:
            Dict cấu hình Kubernetes
        """
        metrics = []

        if self.AUTOSCALING_STRATEGY in ["cpu", "combined"]:
            metrics.append(
                {
                    "type": "Resource",
                    "resource": {
                        "name": "cpu",
                        "target": {
                            "type": "Utilization",
                            "averageUtilization": self.AUTOSCALING_CPU_THRESHOLD,
                        },
                    },
                }
            )

        if self.AUTOSCALING_STRATEGY in ["memory", "combined"]:
            metrics.append(
                {
                    "type": "Resource",
                    "resource": {
                        "name": "memory",
                        "target": {
                            "type": "Utilization",
                            "averageUtilization": self.AUTOSCALING_MEMORY_THRESHOLD,
                        },
                    },
                }
            )

        return {
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "spec": {
                "minReplicas": self.AUTOSCALING_MIN_REPLICAS,
                "maxReplicas": self.AUTOSCALING_MAX_REPLICAS,
                "metrics": metrics,
                "behavior": {
                    "scaleUp": {
                        "stabilizationWindowSeconds": self.AUTOSCALING_SCALE_UP_COOLDOWN,
                        "policies": [
                            {
                                "type": "Percent",
                                "value": self.AUTOSCALING_SCALE_UP_FACTOR,
                                "periodSeconds": 60,
                            }
                        ],
                    },
                    "scaleDown": {
                        "stabilizationWindowSeconds": self.AUTOSCALING_SCALE_DOWN_COOLDOWN,
                        "policies": [
                            {
                                "type": "Percent",
                                "value": self.AUTOSCALING_SCALE_DOWN_FACTOR,
                                "periodSeconds": 60,
                            }
                        ],
                    },
                },
            },
        }


# Khởi tạo cấu hình
autoscaling_config = AutoscalingConfig()
