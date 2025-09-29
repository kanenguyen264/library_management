"""
Database utilities for SQLAlchemy ORM models.

This module provides utilities for working with SQLAlchemy models,
including conversion between models and dictionaries and common CRUD operations.
"""

from app.common.db.model import Model, model_to_dict
from app.common.db.base_class import Base

__all__ = ["Model", "model_to_dict", "Base"]
