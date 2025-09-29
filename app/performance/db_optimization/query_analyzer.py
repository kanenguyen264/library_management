import time
import functools
import logging
import json
from typing import Dict, List, Any, Optional, Callable, Set, Union, Tuple, Type
from contextlib import contextmanager
import asyncio
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session
import threading
from datetime import datetime, timedelta
from collections import defaultdict
import re

from app.core.config import get_settings
from app.logging.setup import get_logger
from prometheus_client import Histogram, Counter, Summary

settings = get_settings()
logger = get_logger(__name__)

# Local thread storage for query tracking
_local = threading.local()

# Prometheus metrics
DB_QUERY_EXECUTION_TIME = Histogram(
    "db_query_execution_time_seconds",
    "Thời gian thực thi truy vấn DB",
    ["operation", "table", "statement_type"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
)

DB_QUERY_COUNT = Counter(
    "db_query_count", "Số lượng truy vấn DB", ["operation", "table", "statement_type"]
)

DB_QUERY_ROWS = Summary(
    "db_query_rows", "Số lượng rows ảnh hưởng bởi truy vấn", ["operation", "table"]
)


class QueryOptimizationRecommendation:
    """Đối tượng chứa các khuyến nghị tối ưu truy vấn."""

    def __init__(self, query_id: str, original_query: str):
        self.query_id = query_id
        self.original_query = original_query
        self.recommendations = []
        self.performance_impact = "unknown"  # low, medium, high
        self.security_impact = "unknown"
        self.difficulty = "unknown"
        self.estimated_speedup = None

    def add_recommendation(
        self, title: str, description: str, code_example: str = None
    ):
        self.recommendations.append(
            {"title": title, "description": description, "code_example": code_example}
        )

    def set_impact(
        self,
        performance: str,
        security: str,
        difficulty: str,
        estimated_speedup: float = None,
    ):
        self.performance_impact = performance
        self.security_impact = security
        self.difficulty = difficulty
        self.estimated_speedup = estimated_speedup


class QueryAnalyzer:
    """
    Phân tích và tối ưu hóa các truy vấn database
    """

    def __init__(self, db_session, metrics_client=None, tracing_enabled=True):
        self.db_session = db_session
        self.metrics_client = metrics_client
        self.tracing_enabled = tracing_enabled
        self.query_patterns = {}
        self.query_stats = {}
        self.security_patterns = self._load_security_patterns()

    def _load_security_patterns(self):
        """Tải các mẫu SQL injection và các vấn đề bảo mật khác"""
        return {
            "sql_injection": [
                r"(\%27)|(\')|(\-\-)|(\%23)|(#)",
                r"((\%3D)|(=))[^\n]*((\%27)|(\')|(\-\-)|(\%3B)|(;))",
            ],
            "union_attack": [
                r"union\s+select",
                r"union\s+all\s+select",
            ],
            "command_execution": [
                r"exec\s+\(",
                r"execute\s+\(",
            ],
        }

    async def analyze_query(self, query: str, params=None, explain=True):
        """Phân tích một truy vấn SQL để tìm vấn đề hiệu suất và bảo mật"""
        query_id = self._generate_query_id(query)

        # Kiểm tra bảo mật
        security_issues = self._check_security(query, params)

        # Phân tích hiệu suất
        perf_issues = []
        explain_result = None

        if explain:
            try:
                explain_result = await self._get_explain_plan(query, params)
                perf_issues = self._analyze_explain_plan(explain_result)
            except Exception as e:
                perf_issues.append(f"Không thể lấy explain plan: {str(e)}")

        # Đề xuất cải tiến
        recommendation = QueryOptimizationRecommendation(query_id, query)

        # Thêm các khuyến nghị bảo mật
        if security_issues:
            for issue in security_issues:
                recommendation.add_recommendation(
                    f"Vấn đề bảo mật: {issue['type']}",
                    issue["description"],
                    issue.get("fix"),
                )
            recommendation.set_impact("unknown", "high", "medium")

        # Thêm các khuyến nghị hiệu suất
        estimated_speedup = None
        if perf_issues:
            for issue in perf_issues:
                if isinstance(issue, dict):
                    recommendation.add_recommendation(
                        issue["title"], issue["description"], issue.get("fix")
                    )
                    if "speedup" in issue:
                        estimated_speedup = issue["speedup"]
                else:
                    recommendation.add_recommendation(
                        "Vấn đề hiệu suất", str(issue), None
                    )

            performance_impact = "medium"
            if estimated_speedup:
                if estimated_speedup > 5:
                    performance_impact = "high"
                elif estimated_speedup < 2:
                    performance_impact = "low"

            if not security_issues:  # Chỉ cập nhật nếu chưa có vấn đề bảo mật
                recommendation.set_impact(
                    performance_impact, "low", "medium", estimated_speedup
                )

        # Lưu trữ thống kê truy vấn
        self._record_query_stats(query_id, query, security_issues, perf_issues)

        return recommendation

    def _generate_query_id(self, query: str) -> str:
        """Tạo ID cho truy vấn để theo dõi"""
        import hashlib

        normalized_query = self._normalize_query(query)
        return hashlib.md5(normalized_query.encode()).hexdigest()

    def _normalize_query(self, query: str) -> str:
        """Chuẩn hóa truy vấn để gom nhóm các truy vấn tương tự"""
        import re

        # Thay thế các giá trị cụ thể bằng placeholders
        normalized = re.sub(r"\'[^\']*\'", "?", query)
        normalized = re.sub(r"\d+", "?", normalized)
        # Loại bỏ khoảng trắng thừa
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _check_security(self, query: str, params=None):
        """Kiểm tra các vấn đề bảo mật trong truy vấn"""
        issues = []

        # Kiểm tra truy vấn SQL
        for pattern_type, patterns in self.security_patterns.items():
            for pattern in patterns:
                import re

                if re.search(pattern, query, re.IGNORECASE):
                    issues.append(
                        {
                            "type": pattern_type,
                            "description": f"Phát hiện mẫu {pattern_type} tiềm ẩn trong truy vấn",
                            "fix": "Sử dụng tham số được gán giá trị và ORM thay vì nối chuỗi SQL",
                        }
                    )
                    break

        # Kiểm tra raw SQL trong parameters
        if params:
            for param in params:
                if isinstance(param, str) and any(
                    char in param for char in ["'", "--", ";", "/*", "*/"]
                ):
                    issues.append(
                        {
                            "type": "parameter_injection",
                            "description": "Tham số chứa ký tự SQL đặc biệt",
                            "fix": "Kiểm tra và làm sạch tham số đầu vào trước khi sử dụng",
                        }
                    )

        return issues

    async def _get_explain_plan(self, query: str, params=None):
        """Lấy explain plan của truy vấn"""
        # Chuẩn bị truy vấn EXPLAIN
        explain_query = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}"

        # Thực thi explain
        async with self.db_session.connection() as conn:
            result = await conn.execute(explain_query, params)
            return await result.fetchone()

    def _analyze_explain_plan(self, explain_result):
        """Phân tích explain plan và tìm vấn đề hiệu suất"""
        issues = []

        try:
            plan = explain_result[0]

            # Kiểm tra sequential scan
            if self._has_sequential_scan(plan):
                issues.append(
                    {
                        "title": "Sequential Scan phát hiện",
                        "description": "Truy vấn đang thực hiện sequential scan trên bảng lớn. Hãy xem xét thêm index.",
                        "fix": "CREATE INDEX idx_name ON table_name (column_name);",
                        "speedup": 3.5,
                    }
                )

            # Kiểm tra nested loops với nhiều rows
            if self._has_inefficient_joins(plan):
                issues.append(
                    {
                        "title": "Join không hiệu quả",
                        "description": "Truy vấn sử dụng nested loop join với nhiều dòng. Hãy xem xét cải thiện index hoặc điều kiện join.",
                        "speedup": 2.0,
                    }
                )

            # Phát hiện temporary files
            if self._has_temp_files(plan):
                issues.append(
                    {
                        "title": "Temporary files",
                        "description": "Truy vấn tạo temporary files lớn. Hãy xem xét tăng work_mem hoặc tối ưu truy vấn.",
                        "speedup": 1.8,
                    }
                )

        except Exception as e:
            issues.append(f"Lỗi khi phân tích explain plan: {str(e)}")

        return issues

    def _has_sequential_scan(self, plan):
        """Kiểm tra sequential scan trong explain plan"""
        if isinstance(plan, dict):
            node_type = plan.get("Node Type")
            if node_type == "Seq Scan" and plan.get("Plan Rows", 0) > 1000:
                return True

            for key, value in plan.items():
                if isinstance(value, (dict, list)) and self._has_sequential_scan(value):
                    return True

        elif isinstance(plan, list):
            for item in plan:
                if self._has_sequential_scan(item):
                    return True

        return False

    def _has_inefficient_joins(self, plan):
        """Kiểm tra joins không hiệu quả trong explain plan"""
        if isinstance(plan, dict):
            node_type = plan.get("Node Type")
            if node_type == "Nested Loop" and plan.get("Plan Rows", 0) > 1000:
                return True

            for key, value in plan.items():
                if isinstance(value, (dict, list)) and self._has_inefficient_joins(
                    value
                ):
                    return True

        elif isinstance(plan, list):
            for item in plan:
                if self._has_inefficient_joins(item):
                    return True

        return False

    def _has_temp_files(self, plan):
        """Kiểm tra temporary files trong explain plan"""
        temp_file_indicators = [
            "Temporary File",
            "Sort Method: external",
            "Sort Method: external merge",
        ]

        if isinstance(plan, dict):
            for indicator in temp_file_indicators:
                if indicator in str(plan):
                    return True

            for key, value in plan.items():
                if isinstance(value, (dict, list)) and self._has_temp_files(value):
                    return True

        elif isinstance(plan, list):
            for item in plan:
                if self._has_temp_files(item):
                    return True

        return False

    def _record_query_stats(self, query_id, query, security_issues, perf_issues):
        """Ghi lại thống kê truy vấn để phân tích về sau"""
        if query_id not in self.query_stats:
            self.query_stats[query_id] = {
                "query": query,
                "normalized_query": self._normalize_query(query),
                "execution_count": 0,
                "security_issues": [],
                "performance_issues": [],
                "last_seen": None,
            }

        stats = self.query_stats[query_id]
        stats["execution_count"] += 1
        stats["last_seen"] = time.time()

        # Cập nhật vấn đề bảo mật
        for issue in security_issues:
            if issue not in stats["security_issues"]:
                stats["security_issues"].append(issue)

        # Cập nhật vấn đề hiệu suất
        for issue in perf_issues:
            if issue not in stats["performance_issues"]:
                stats["performance_issues"].append(issue)

        # Gửi metrics nếu có
        if self.metrics_client:
            try:
                self.metrics_client.increment(
                    "db.query.execution_count", tags={"query_id": query_id}
                )

                if security_issues:
                    self.metrics_client.increment(
                        "db.query.security_issues",
                        value=len(security_issues),
                        tags={"query_id": query_id},
                    )

                if perf_issues:
                    self.metrics_client.increment(
                        "db.query.perf_issues",
                        value=len(perf_issues),
                        tags={"query_id": query_id},
                    )
            except Exception:
                pass

    async def get_slow_queries(self, limit=10):
        """Lấy danh sách các truy vấn chậm nhất"""
        # Giả định: Thông tin này có thể lấy từ PostgreSQL pg_stat_statements
        query = """
        SELECT query, calls, total_time / calls AS avg_time, 
               rows, shared_blks_hit, shared_blks_read
        FROM pg_stat_statements
        ORDER BY avg_time DESC
        LIMIT :limit
        """

        try:
            async with self.db_session.connection() as conn:
                result = await conn.execute(query, {"limit": limit})
                rows = await result.fetchall()

                slow_queries = []
                for row in rows:
                    # Tạo đề xuất cho mỗi truy vấn chậm
                    recommendation = await self.analyze_query(row.query)
                    slow_queries.append(
                        {
                            "query": row.query,
                            "avg_time_ms": row.avg_time,
                            "calls": row.calls,
                            "rows": row.rows,
                            "recommendation": recommendation,
                        }
                    )

                return slow_queries
        except Exception as e:
            return [{"error": f"Không thể lấy truy vấn chậm: {str(e)}"}]

    async def optimize_query(self, query: str, params=None):
        """Tự động tối ưu truy vấn SQL"""
        # Phân tích truy vấn
        recommendation = await self.analyze_query(query, params)

        # Nếu không có khuyến nghị, trả về truy vấn gốc
        if not recommendation.recommendations:
            return query

        # Áp dụng các tối ưu hóa
        optimized_query = query

        # Duyệt qua từng khuyến nghị
        for rec in recommendation.recommendations:
            if "Sequential Scan" in rec["title"] and rec.get("code_example"):
                # Không thực sự sửa truy vấn, chỉ ghi chú
                optimized_query = (
                    f"/* Recommended index: {rec['code_example']} */\n"
                    + optimized_query
                )

            elif "Join không hiệu quả" in rec["title"]:
                # Thêm gợi ý HASH JOIN hoặc MERGE JOIN
                if (
                    "MERGE JOIN" not in optimized_query
                    and "HASH JOIN" not in optimized_query
                ):
                    # Thêm hint cho PostgreSQL (chỉ hoạt động với một số phiên bản)
                    optimized_query = f"/*+ HASHJOIN */\n" + optimized_query

        return optimized_query

    def generate_index_recommendations(self):
        """Tạo các khuyến nghị về index dựa trên phân tích truy vấn"""
        recommendations = []

        # Trong một ứng dụng thực, chúng ta sẽ phân tích pg_stat_statements và pg_stat_user_tables
        # để tạo khuyến nghị. Dưới đây là một ví dụ đơn giản.

        # Ví dụ về index recommendation:
        recommendations.append(
            {
                "table": "books",
                "columns": ["author_id"],
                "reason": "Phát hiện nhiều sequential scan trên books theo author_id",
                "sql": "CREATE INDEX idx_books_author_id ON books (author_id);",
                "estimated_impact": "high",
            }
        )

        recommendations.append(
            {
                "table": "reviews",
                "columns": ["book_id", "created_at"],
                "reason": "Frequently filtered by book_id and sorted by created_at",
                "sql": "CREATE INDEX idx_reviews_book_created ON reviews (book_id, created_at DESC);",
                "estimated_impact": "medium",
            }
        )

        return recommendations

    def identify_n_plus_one_queries(self, query_log):
        """Xác định vấn đề N+1 query dựa trên nhật ký truy vấn"""
        suspected_patterns = []

        # Analyze log for patterns of repeated similar queries
        query_patterns = {}

        for entry in query_log:
            query = entry["query"]
            normalized = self._normalize_query(query)

            if normalized not in query_patterns:
                query_patterns[normalized] = []

            query_patterns[normalized].append(entry)

        # Look for patterns that appear in bursts (potential N+1)
        for pattern, entries in query_patterns.items():
            if len(entries) > 5:
                # Check if these queries happened close in time
                entries.sort(key=lambda x: x.get("timestamp", 0))
                time_diffs = []

                for i in range(1, len(entries)):
                    time_diff = entries[i].get("timestamp", 0) - entries[i - 1].get(
                        "timestamp", 0
                    )
                    time_diffs.append(time_diff)

                # If median time difference is small, likely N+1
                if len(time_diffs) > 0:
                    import statistics

                    try:
                        median_diff = statistics.median(time_diffs)
                        if median_diff < 0.1:  # Less than 100ms between queries
                            suspected_patterns.append(
                                {
                                    "pattern": pattern,
                                    "count": len(entries),
                                    "sample_query": entries[0]["query"],
                                    "fix": "Sử dụng eager loading hoặc joins thay vì N+1 queries",
                                }
                            )
                    except Exception:
                        pass

        return suspected_patterns

    def calculate_database_metrics(self):
        """Tính toán các metrics về hiệu suất cơ sở dữ liệu"""
        # Trong ứng dụng thực, chúng ta sẽ truy vấn pg_stat_database, pg_stat_bgwriter, v.v.
        # Đây chỉ là ví dụ
        return {
            "cache_hit_ratio": 0.95,  # 95% cache hit
            "index_usage": 0.85,  # 85% of queries use indexes
            "table_bloat": [
                {"table": "users", "bloat_factor": 1.2},
                {"table": "books", "bloat_factor": 1.5},
            ],
            "slow_query_count": 25,
            "deadlock_count": 0,
            "suggestions": [
                "VACUUM ANALYZE trên bảng books để giảm bloat",
                "Xem xét thêm index cho trường 'published_date' trên bảng books",
            ],
        }


# Thay thế singleton instance bằng một factory function để tạo instance khi cần
def get_query_analyzer(db_session=None, metrics_client=None, tracing_enabled=True):
    """
    Factory function để tạo hoặc lấy instance của QueryAnalyzer.

    Args:
        db_session: Database session
        metrics_client: Client để ghi metrics
        tracing_enabled: Có bật tracing không

    Returns:
        QueryAnalyzer instance
    """
    # Sử dụng "Lazy Initialization" - không tạo instance cho đến khi có db_session
    if db_session is None:
        # Trả về một dummy analyzer trong trường hợp không có session
        from types import SimpleNamespace

        # Dummy track function
        def dummy_track(*args, **kwargs):
            def decorator(func):
                return func

            return decorator

        # Tạo dummy object
        dummy = SimpleNamespace(
            analyze_query=lambda *args, **kwargs: None,
            track=dummy_track,
            get_slow_queries=lambda *args, **kwargs: [],
            optimize_query=lambda *args, **kwargs: None,
            generate_index_recommendations=lambda: [],
            identify_n_plus_one_queries=lambda *args: [],
            calculate_database_metrics=lambda: {},
        )

        return dummy

    # Tạo và trả về instance thực
    return QueryAnalyzer(db_session, metrics_client, tracing_enabled)


# Context manager tiện ích
# Lấy track function từ factory
def track(*args, **kwargs):
    # Sử dụng function từ query_analyzer instance được tạo lazily
    return get_query_analyzer().track(*args, **kwargs)
