from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Float,
    DateTime,
    Boolean,
    Index,
    func,
)
from app.core.db import Base


class Promotion(Base):
    __tablename__ = "promotions"
    __table_args__ = (
        Index("idx_promotions_name", "name"),
        Index("idx_promotions_coupon_code", "coupon_code"),
        Index("idx_promotions_start_date", "start_date"),
        Index("idx_promotions_end_date", "end_date"),
        Index("idx_promotions_is_active", "is_active"),
        {"schema": "admin"},
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    discount_type = Column(String(50), nullable=False)  # percentage, fixed_amount
    discount_value = Column(Float, nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)
    coupon_code = Column(String(100), nullable=True, unique=True)
    usage_limit = Column(Integer, nullable=True)
    usage_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
