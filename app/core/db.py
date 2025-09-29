"""
Core database module for the application.

This module provides the database engine, session factory, and other database-related utilities.
"""

from typing import AsyncGenerator, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, DateTime, Boolean, Integer, String, func, event, text
from sqlalchemy.ext.declarative import declared_attr
import logging
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger("db")


# Create custom base class with enhanced features
class CustomBase:
    """Base class for all models with common columns and utility methods."""

    # Common columns for all models
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Utilities for models
    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary excluding SQLAlchemy internal attributes."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Any:
        """Create model instance from dictionary."""
        return cls(
            **{k: v for k, v in data.items() if k in cls.__table__.columns.keys()}
        )

    def update_from_dict(self, data: Dict[str, Any]) -> None:
        """Update model from dictionary."""
        for key, value in data.items():
            if hasattr(self, key) and key in self.__table__.columns.keys():
                setattr(self, key, value)


# Create declarative base with the custom base
Base = declarative_base(cls=CustomBase)

# Create async engine
engine = create_async_engine(
    str(settings.DATABASE_URL),
    echo=getattr(settings, "DB_ECHO", False),
    pool_size=getattr(settings, "DATABASE_POOL_SIZE", 20),
    max_overflow=getattr(settings, "DATABASE_MAX_OVERFLOW", 10),
    pool_pre_ping=True,
)

# Create async session factory
async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database session as a dependency.

    Yields:
        AsyncSession: SQLAlchemy async session
    """
    async with async_session() as session:
        try:
            # Test the connection to ensure it's valid
            try:
                await session.execute(text("SELECT 1"))
            except SQLAlchemyError as e:
                logger.error(f"Database connection error: {e}")
                raise

            yield session
        except SQLAlchemyError as e:
            logger.error(f"Session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_database_connection() -> bool:
    """
    Check if database connection is working.
    Returns True if connection is successful, False otherwise.
    """
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
            return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False
