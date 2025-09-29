"""
Chiến lược vô hiệu hóa cache dựa trên truy vấn (query).

Chiến lược này theo dõi và phân tích các truy vấn database để xác định
khi nào cache cần được vô hiệu hóa dựa trên dữ liệu thay đổi.
"""

from typing import Dict, List, Any, Optional, Union, Set, Tuple, Callable
import sqlparse

from app.logging.setup import get_logger
from app.cache.manager import cache_manager

logger = get_logger(__name__)


class QueryAnalyzer:
    """
    Phân tích SQL query để xác định các bảng và thao tác liên quan.
    """

    @staticmethod
    def extract_tables(query: str) -> List[str]:
        """
        Trích xuất tên bảng từ câu truy vấn SQL.

        Args:
            query: Câu truy vấn SQL

        Returns:
            Danh sách tên bảng
        """
        # Phân tích câu truy vấn
        parsed = sqlparse.parse(query)
        if not parsed:
            return []

        # Lấy statement đầu tiên
        statement = parsed[0]

        # Danh sách tên bảng
        tables = []

        # Tìm các token FROM, JOIN,... và lấy tên bảng theo sau
        tokens = statement.tokens
        for i, token in enumerate(tokens):
            # Tìm các keyword
            if token.ttype is sqlparse.tokens.Keyword and token.value.upper() in [
                "FROM",
                "JOIN",
                "UPDATE",
                "INTO",
            ]:
                # Lấy token tiếp theo (bỏ qua whitespace)
                for j in range(i + 1, len(tokens)):
                    next_token = tokens[j]
                    if not next_token.is_whitespace:
                        # Xử lý tên bảng
                        if hasattr(next_token, "tokens"):
                            # Token có thể là một group (ví dụ: "schema.table")
                            table_name = next_token.value.strip("\"'`[]")
                            tables.append(
                                table_name.split(".")[-1]
                            )  # Chỉ lấy phần tên bảng
                        else:
                            tables.append(next_token.value.strip("\"'`[]"))
                        break

        # Thêm xử lý cho DELETE FROM
        if statement.get_type() == "DELETE":
            for i, token in enumerate(tokens):
                if (
                    token.ttype is sqlparse.tokens.Keyword.DML
                    and token.value.upper() == "DELETE"
                ):
                    # Tìm FROM sau DELETE
                    for j in range(i + 1, len(tokens)):
                        if (
                            tokens[j].ttype is sqlparse.tokens.Keyword
                            and tokens[j].value.upper() == "FROM"
                        ):
                            # Lấy token tiếp theo (bỏ qua whitespace)
                            for k in range(j + 1, len(tokens)):
                                next_token = tokens[k]
                                if not next_token.is_whitespace:
                                    # Xử lý tên bảng
                                    tables.append(next_token.value.strip("\"'`[]"))
                                    break
                            break
                    break

        return tables

    @staticmethod
    def get_operation_type(query: str) -> str:
        """
        Xác định loại thao tác của câu truy vấn SQL.

        Args:
            query: Câu truy vấn SQL

        Returns:
            Loại thao tác (SELECT, INSERT, UPDATE, DELETE)
        """
        # Phân tích câu truy vấn
        parsed = sqlparse.parse(query)
        if not parsed:
            return "UNKNOWN"

        # Lấy statement đầu tiên
        statement = parsed[0]

        # Lấy loại statement
        statement_type = statement.get_type()
        if statement_type:
            return statement_type.upper()

        # Nếu không xác định được, tìm từ khóa đầu tiên
        for token in statement.tokens:
            if token.ttype is sqlparse.tokens.Keyword.DML:
                return token.value.upper()

        return "UNKNOWN"

    @staticmethod
    def is_write_operation(query: str) -> bool:
        """
        Kiểm tra xem câu truy vấn có thay đổi dữ liệu hay không.

        Args:
            query: Câu truy vấn SQL

        Returns:
            True nếu là thao tác ghi (INSERT, UPDATE, DELETE)
        """
        op_type = QueryAnalyzer.get_operation_type(query)
        return op_type in ["INSERT", "UPDATE", "DELETE"]


class QueryBasedStrategy:
    """
    Chiến lược vô hiệu hóa cache dựa trên truy vấn.

    Theo dõi và phân tích các truy vấn database để xác định
    khi nào cache cần được vô hiệu hóa dựa trên dữ liệu thay đổi.
    """

    def __init__(
        self,
        table_pattern_mapping: Dict[str, List[str]] = None,
        table_tag_mapping: Dict[str, List[str]] = None,
        table_namespace_mapping: Dict[str, str] = None,
        track_all_tables: bool = False,
    ):
        """
        Khởi tạo strategy vô hiệu hóa dựa trên truy vấn.

        Args:
            table_pattern_mapping: Mapping từ tên bảng đến pattern cache cần vô hiệu hóa
            table_tag_mapping: Mapping từ tên bảng đến tag cache cần vô hiệu hóa
            table_namespace_mapping: Mapping từ tên bảng đến namespace cần vô hiệu hóa
            track_all_tables: Theo dõi tất cả các bảng (tự động tạo pattern)
        """
        self.table_pattern_mapping = table_pattern_mapping or {}
        self.table_tag_mapping = table_tag_mapping or {}
        self.table_namespace_mapping = table_namespace_mapping or {}
        self.track_all_tables = track_all_tables
        self.analyzer = QueryAnalyzer()

    async def process_query(self, query: str, params: Any = None) -> None:
        """
        Xử lý câu truy vấn SQL.

        Args:
            query: Câu truy vấn SQL
            params: Tham số của câu truy vấn
        """
        # Chỉ xử lý thao tác ghi
        if not self.analyzer.is_write_operation(query):
            return

        # Lấy danh sách bảng bị ảnh hưởng
        tables = self.analyzer.extract_tables(query)

        if not tables:
            return

        # Vô hiệu hóa cache cho mỗi bảng
        for table in tables:
            await self._invalidate_for_table(table)

    async def _invalidate_for_table(self, table: str) -> None:
        """
        Vô hiệu hóa cache cho một bảng.

        Args:
            table: Tên bảng
        """
        # Vô hiệu hóa theo pattern
        patterns = self.table_pattern_mapping.get(table, [])

        # Nếu track_all_tables và không có pattern cho bảng này
        if self.track_all_tables and not patterns:
            # Tạo pattern mặc định
            patterns = [f"{table}:*"]

        # Vô hiệu hóa theo pattern
        if patterns:
            for pattern in patterns:
                namespace = self.table_namespace_mapping.get(table)
                count = await cache_manager.clear(pattern, namespace)
                logger.info(
                    f"Đã vô hiệu hóa {count} keys theo pattern '{pattern}' cho bảng '{table}'"
                )

        # Vô hiệu hóa theo tag
        tags = self.table_tag_mapping.get(table, [])

        # Nếu track_all_tables và không có tag cho bảng này
        if self.track_all_tables and not tags:
            # Tạo tag mặc định
            tags = [table]

        # Vô hiệu hóa theo tag
        if tags:
            count = await cache_manager.invalidate_by_tags(tags)
            logger.info(
                f"Đã vô hiệu hóa {count} keys theo tags '{', '.join(tags)}' cho bảng '{table}'"
            )

    @classmethod
    def create_default(cls) -> "QueryBasedStrategy":
        """
        Tạo strategy mặc định theo dõi tất cả các bảng.

        Returns:
            QueryBasedStrategy instance
        """
        return cls(track_all_tables=True)

    @classmethod
    def create_for_models(cls, model_mapping: Dict[str, str]) -> "QueryBasedStrategy":
        """
        Tạo strategy cho các model.

        Args:
            model_mapping: Mapping từ tên model đến tên bảng

        Returns:
            QueryBasedStrategy instance
        """
        # Tạo mapping từ tên bảng đến pattern và tag
        table_pattern_mapping = {}
        table_tag_mapping = {}

        for model_name, table_name in model_mapping.items():
            # Pattern cho model cache
            table_pattern_mapping[table_name] = [
                f"{model_name.lower()}:*",
                f"{model_name.lower()}_list:*",
            ]

            # Tag cho model cache
            table_tag_mapping[table_name] = [model_name.lower()]

        return cls(
            table_pattern_mapping=table_pattern_mapping,
            table_tag_mapping=table_tag_mapping,
            track_all_tables=False,
        )


class SQLAlchemyQueryListener:
    """
    Listener cho SQLAlchemy để theo dõi các truy vấn.
    """

    def __init__(self, strategy: QueryBasedStrategy):
        """
        Khởi tạo listener.

        Args:
            strategy: Strategy để xử lý truy vấn
        """
        self.strategy = strategy

    async def before_execute(
        self, conn, clauseelement, multiparams, params, execution_options
    ):
        """
        Hook được gọi trước khi thực thi truy vấn.

        Args:
            conn: Connection
            clauseelement: Clause element
            multiparams: Multi params
            params: Params
            execution_options: Execution options
        """
        # Chỉ xử lý clause có thuộc tính compile
        if hasattr(clauseelement, "compile"):
            # Compile thành string SQL
            query = str(
                clauseelement.compile(
                    dialect=conn.dialect, compile_kwargs={"literal_binds": True}
                )
            )

            # Xử lý query
            await self.strategy.process_query(query, params)

    async def after_execute(
        self, conn, clauseelement, multiparams, params, execution_options, result
    ):
        """
        Hook được gọi sau khi thực thi truy vấn.

        Args:
            conn: Connection
            clauseelement: Clause element
            multiparams: Multi params
            params: Params
            execution_options: Execution options
            result: Result
        """
        # Không cần xử lý sau khi thực thi
        pass


# Singleton strategy
default_query_strategy = QueryBasedStrategy.create_default()


def setup_sqlalchemy_listener(engine, strategy: QueryBasedStrategy = None):
    """
    Thiết lập listener cho SQLAlchemy engine.

    Args:
        engine: SQLAlchemy engine
        strategy: Strategy để xử lý truy vấn
    """
    from sqlalchemy import event

    # Sử dụng strategy mặc định nếu không có
    if strategy is None:
        strategy = default_query_strategy

    # Tạo listener
    listener = SQLAlchemyQueryListener(strategy)

    # Đăng ký event
    event.listen(engine, "before_execute", listener.before_execute)
    event.listen(engine, "after_execute", listener.after_execute)
