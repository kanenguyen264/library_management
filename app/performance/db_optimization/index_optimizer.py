from typing import Dict, List, Any, Set, Optional, Tuple, Union
import logging
import time
import json
import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.schema import Table, Column, Index
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.orm import Session
import asyncio
import re
from collections import defaultdict
import os
from datetime import datetime

from app.core.config import get_settings
from app.logging.setup import get_logger
from app.performance.db_optimization.query_analyzer import get_query_analyzer

settings = get_settings()
logger = get_logger(__name__)


class IndexOptimizer:
    """
    Tối ưu và quản lý chỉ mục (index) trong cơ sở dữ liệu.
    Cung cấp:
    - Phân tích và đề xuất chỉ mục
    - Tạo chỉ mục tự động
    - Đánh giá hiệu quả của chỉ mục
    - Phát hiện chỉ mục bị trùng lặp hoặc không sử dụng
    """

    def __init__(
        self,
        enabled: bool = None,
        auto_create_indexes: bool = False,
        analyze_queries: bool = True,
        min_query_count: int = 10,
        min_avg_time: float = 0.1,
        log_level: int = logging.INFO,
        index_suggestion_file: Optional[str] = None,
    ):
        """
        Khởi tạo index optimizer.

        Args:
            enabled: Bật/tắt tối ưu index
            auto_create_indexes: Tự động tạo index được đề xuất
            analyze_queries: Phân tích truy vấn để đề xuất index
            min_query_count: Số lượng truy vấn tối thiểu trước khi đề xuất
            min_avg_time: Thời gian truy vấn trung bình tối thiểu (giây)
            log_level: Mức độ ghi log
            index_suggestion_file: File lưu đề xuất index
        """
        # Tự động bật trong môi trường dev, tắt trong production
        if enabled is None:
            self.enabled = not settings.is_production
        else:
            self.enabled = enabled

        self.auto_create_indexes = auto_create_indexes and not settings.is_production
        self.analyze_queries = analyze_queries
        self.min_query_count = min_query_count
        self.min_avg_time = min_avg_time
        self.log_level = log_level

        if index_suggestion_file:
            self.index_suggestion_file = index_suggestion_file
        else:
            self.index_suggestion_file = os.path.join(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                ),
                "logs",
                "index_suggestions.json",
            )

        # Lưu trữ thông tin index
        self.existing_indexes = {}  # {table_name: {column_name: index_name}}
        self.suggested_indexes = set()  # Set of (table_name, column_name)
        self.created_indexes = set()  # Set of (table_name, column_name)
        self.unused_indexes = set()  # Set of (table_name, index_name)
        self.duplicate_indexes = set()  # Set of (table_name, index_name)

        # Đường dẫn lưu đề xuất index
        os.makedirs(os.path.dirname(self.index_suggestion_file), exist_ok=True)

    async def analyze_database_schema(
        self, session: AsyncSession
    ) -> Dict[str, Dict[str, str]]:
        """
        Phân tích schema cơ sở dữ liệu để lấy thông tin về các index hiện có.

        Args:
            session: SQLAlchemy session

        Returns:
            Dict chứa thông tin về các index hiện có
        """
        if not self.enabled:
            return {}

        result = {}

        # Sử dụng reflection để lấy thông tin về các bảng
        try:
            # Get metadata from connection
            metadata = sa.MetaData()
            conn = await session.connection()

            # Reflect tables for all schemas
            query = """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            """
            res = await session.execute(text(query))
            tables = res.fetchall()

            # Analyze each table
            for schema, table in tables:
                schema_table = f"{schema}.{table}" if schema != "public" else table

                # Get existing indexes
                query = text(
                    f"""
                SELECT
                    i.relname as index_name,
                    a.attname as column_name
                FROM
                    pg_catalog.pg_class t,
                    pg_catalog.pg_class i,
                    pg_catalog.pg_index ix,
                    pg_catalog.pg_attribute a,
                    pg_catalog.pg_namespace n
                WHERE
                    t.oid = ix.indrelid
                    AND i.oid = ix.indexrelid
                    AND a.attrelid = t.oid
                    AND a.attnum = ANY(ix.indkey)
                    AND t.relnamespace = n.oid
                    AND t.relname = :table_name
                    AND n.nspname = :schema_name
                ORDER BY
                    t.relname,
                    i.relname;
                """
                )

                params = {"table_name": table, "schema_name": schema}
                res = await session.execute(query, params)
                indexes = res.fetchall()

                # Organize index information
                table_indexes = {}
                for index_name, column_name in indexes:
                    if column_name not in table_indexes:
                        table_indexes[column_name] = index_name

                result[schema_table] = table_indexes

            self.existing_indexes = result
            logger.info(
                f"Đã phân tích {len(result)} bảng và tìm thấy index cho {sum(len(idx) for idx in result.values())} cột"
            )
            return result

        except Exception as e:
            logger.error(f"Lỗi khi phân tích schema cơ sở dữ liệu: {str(e)}")
            return {}

    async def suggest_indexes(self, session: AsyncSession) -> List[Dict[str, Any]]:
        """
        Đề xuất các index cần tạo dựa trên phân tích truy vấn.

        Args:
            session: SQLAlchemy session

        Returns:
            Danh sách các index được đề xuất
        """
        if not self.enabled or not self.analyze_queries:
            return []

        # Make sure we have analyzed the schema
        if not self.existing_indexes:
            await self.analyze_database_schema(session)

        # Get suggested indexes from query analyzer
        analyzer = get_query_analyzer(db_session=session)
        index_suggestions = analyzer.generate_index_recommendations()
        suggested_indexes = []

        for table, columns in index_suggestions.items():
            for column in columns:
                # Check if index already exists
                existing_table_indexes = self.existing_indexes.get(table, {})
                if column in existing_table_indexes:
                    continue

                # Check if already suggested
                if (table, column) in self.suggested_indexes:
                    continue

                # Get query stats for this table
                query_key = f"SELECT {table}"
                query_stats = (
                    analyzer.query_stats.get(query_key, {})
                    if hasattr(analyzer, "query_stats")
                    else {}
                )

                # Only suggest if query meets minimum criteria
                if (
                    query_stats.get("count", 0) >= self.min_query_count
                    and query_stats.get("avg_time", 0) >= self.min_avg_time
                ):
                    self.suggested_indexes.add((table, column))

                    suggested_indexes.append(
                        {
                            "table": table,
                            "column": column,
                            "query_count": query_stats.get("count", 0),
                            "avg_time": query_stats.get("avg_time", 0),
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

        # Save suggestions to file
        if suggested_indexes:
            self._save_suggestions(suggested_indexes)

            # Log suggestions
            for suggestion in suggested_indexes:
                logger.warning(
                    f"Đề xuất tạo index cho bảng {suggestion['table']} "
                    f"trên cột {suggestion['column']} "
                    f"(truy vấn: {suggestion['query_count']}, "
                    f"thời gian trung bình: {suggestion['avg_time']:.4f}s)"
                )

            # Create indexes if configured
            if self.auto_create_indexes:
                await self.create_suggested_indexes(session, suggested_indexes)

        return suggested_indexes

    async def create_suggested_indexes(
        self, session: AsyncSession, suggestions: Optional[List[Dict[str, Any]]] = None
    ) -> List[str]:
        """
        Tạo các index được đề xuất.

        Args:
            session: SQLAlchemy session
            suggestions: Danh sách đề xuất hoặc None để sử dụng đề xuất gần nhất

        Returns:
            Danh sách các index đã tạo
        """
        if not self.enabled or not self.auto_create_indexes:
            return []

        # If no suggestions provided, use the last saved suggestions
        if not suggestions:
            try:
                with open(self.index_suggestion_file, "r") as f:
                    suggestions = json.load(f)
            except Exception as e:
                logger.error(f"Lỗi khi đọc file đề xuất index: {str(e)}")
                return []

        # Create suggested indexes
        created_indexes = []

        for suggestion in suggestions:
            table = suggestion["table"]
            column = suggestion["column"]

            # Check if already created
            if (table, column) in self.created_indexes:
                continue

            # Check if index already exists
            existing_table_indexes = self.existing_indexes.get(table, {})
            if column in existing_table_indexes:
                continue

            try:
                # Parse schema and table name
                schema = None
                table_name = table

                if "." in table:
                    schema, table_name = table.split(".", 1)

                # Generate index name
                index_name = f"idx_{table_name}_{column}"

                # Create index
                index_stmt = text(
                    f"CREATE INDEX IF NOT EXISTS {index_name} ON "
                    f"{schema+'.' if schema else ''}{table_name} ({column})"
                )

                await session.execute(index_stmt)
                await session.commit()

                # Update tracking
                self.created_indexes.add((table, column))
                created_indexes.append(index_name)

                logger.info(
                    f"Đã tạo index {index_name} trên bảng {table} (cột {column})"
                )

            except Exception as e:
                await session.rollback()
                logger.error(
                    f"Lỗi khi tạo index trên bảng {table} (cột {column}): {str(e)}"
                )

        return created_indexes

    async def analyze_index_usage(self, session: AsyncSession) -> Dict[str, List[str]]:
        """
        Phân tích việc sử dụng các index hiện có.

        Args:
            session: SQLAlchemy session

        Returns:
            Dict chứa thông tin về các index không sử dụng và trùng lặp
        """
        if not self.enabled:
            return {"unused": [], "duplicate": []}

        unused_indexes = []
        duplicate_indexes = []

        try:
            # Query PostgreSQL stats to find unused indexes
            query = text(
                """
            SELECT
                schemaname || '.' || relname as table_name,
                indexrelname as index_name,
                idx_scan as index_scans
            FROM
                pg_stat_user_indexes
            WHERE
                idx_scan = 0
                AND idx_tup_read = 0
                AND idx_tup_fetch = 0
            ORDER BY
                schemaname, relname, indexrelname;
            """
            )

            res = await session.execute(query)
            unused = res.fetchall()

            # Collect unused indexes
            for table_name, index_name, _ in unused:
                unused_indexes.append(f"{table_name}.{index_name}")
                self.unused_indexes.add((table_name, index_name))

            # Query to find duplicate indexes
            query = text(
                """
            SELECT
                schemaname || '.' || tablename as table_name,
                array_agg(indexname) as index_names
            FROM
                (SELECT
                    schemaname,
                    tablename,
                    indexname,
                    array_agg(attname ORDER BY attnum) as columns
                FROM
                    pg_index i
                    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                    JOIN pg_class c ON c.oid = i.indrelid
                    JOIN pg_class ci ON ci.oid = i.indexrelid
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE
                    n.nspname NOT IN ('pg_catalog', 'pg_toast')
                GROUP BY
                    schemaname, tablename, indexname) t
            GROUP BY
                schemaname, tablename, columns
            HAVING
                COUNT(*) > 1;
            """
            )

            res = await session.execute(query)
            duplicates = res.fetchall()

            # Collect duplicate indexes
            for table_name, index_array in duplicates:
                for index_name in index_array:
                    duplicate_indexes.append(f"{table_name}.{index_name}")
                    self.duplicate_indexes.add((table_name, index_name))

            # Log findings
            if unused_indexes:
                logger.warning(
                    f"Phát hiện {len(unused_indexes)} index không được sử dụng"
                )
                for idx in unused_indexes[:10]:  # Limit to 10 logs
                    logger.warning(f"Index không sử dụng: {idx}")

            if duplicate_indexes:
                logger.warning(f"Phát hiện {len(duplicate_indexes)} index trùng lặp")
                for idx in duplicate_indexes[:10]:  # Limit to 10 logs
                    logger.warning(f"Index trùng lặp: {idx}")

            return {"unused": unused_indexes, "duplicate": duplicate_indexes}

        except Exception as e:
            logger.error(f"Lỗi khi phân tích việc sử dụng index: {str(e)}")
            return {"unused": [], "duplicate": []}

    async def drop_unused_indexes(
        self, session: AsyncSession, confirm: bool = False
    ) -> List[str]:
        """
        Xóa các index không sử dụng.

        Args:
            session: SQLAlchemy session
            confirm: Xác nhận xóa index

        Returns:
            Danh sách các index đã xóa
        """
        if not self.enabled or not confirm:
            return []

        # Ensure we have analyzed index usage
        if not self.unused_indexes:
            await self.analyze_index_usage(session)

        dropped_indexes = []

        for table_name, index_name in self.unused_indexes:
            try:
                # Parse schema and table name
                schema = None
                table = table_name

                if "." in table_name:
                    schema, table = table_name.split(".", 1)

                # Drop index
                index_name_full = f"{schema+'.' if schema else ''}{index_name}"
                drop_stmt = text(f"DROP INDEX IF EXISTS {index_name_full}")

                await session.execute(drop_stmt)
                await session.commit()

                dropped_indexes.append(index_name_full)
                logger.info(f"Đã xóa index không sử dụng: {index_name_full}")

            except Exception as e:
                await session.rollback()
                logger.error(f"Lỗi khi xóa index {index_name}: {str(e)}")

        return dropped_indexes

    def _save_suggestions(self, suggestions: List[Dict[str, Any]]) -> None:
        """
        Lưu đề xuất index vào file.

        Args:
            suggestions: Danh sách đề xuất
        """
        try:
            # Load existing suggestions if file exists
            existing_suggestions = []
            if os.path.exists(self.index_suggestion_file):
                with open(self.index_suggestion_file, "r") as f:
                    existing_suggestions = json.load(f)

            # Merge suggestions
            merged_suggestions = []
            existing_tables_columns = set(
                (s["table"], s["column"]) for s in existing_suggestions
            )

            # Add existing suggestions
            merged_suggestions.extend(existing_suggestions)

            # Add new suggestions
            for suggestion in suggestions:
                if (
                    suggestion["table"],
                    suggestion["column"],
                ) not in existing_tables_columns:
                    merged_suggestions.append(suggestion)

            # Write back to file
            with open(self.index_suggestion_file, "w") as f:
                json.dump(merged_suggestions, f, indent=2)

        except Exception as e:
            logger.error(f"Lỗi khi lưu đề xuất index: {str(e)}")


# Tạo singleton instance
index_optimizer = IndexOptimizer()
