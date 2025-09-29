from typing import Dict, List, Any, Optional, Union, Set, Tuple
import hashlib
import json
import re
from datetime import datetime


class CacheKeyBuilder:
    """
    Class giúp xây dựng cache key với nhiều tùy chọn.

    Cho phép tạo cache key từ nhiều thành phần như prefix, namespace, data.
    Hỗ trợ tùy chỉnh cách xử lý cho từng loại dữ liệu.
    """

    def __init__(
        self,
        prefix: Optional[str] = None,
        namespace: Optional[str] = None,
        include_types: bool = False,
    ):
        """
        Khởi tạo CacheKeyBuilder.

        Args:
            prefix: Tiền tố cho cache key
            namespace: Namespace cho cache key
            include_types: Có thêm kiểu dữ liệu vào key
        """
        self.prefix = prefix
        self.namespace = namespace
        self.include_types = include_types
        self.parts = []

        # Thêm prefix và namespace
        if prefix:
            self.parts.append(str(prefix))
        if namespace:
            self.parts.append(str(namespace))

    def add(self, value: Any) -> "CacheKeyBuilder":
        """
        Thêm giá trị vào cache key.

        Args:
            value: Giá trị cần thêm

        Returns:
            Self reference cho method chaining
        """
        # Xử lý giá trị
        if isinstance(value, (dict, list, tuple, set)):
            # Hash cho các cấu trúc dữ liệu phức tạp
            value_str = hashlib.md5(
                json.dumps(value, sort_keys=True, default=str).encode()
            ).hexdigest()
        elif isinstance(value, datetime):
            # Format datetime
            value_str = value.isoformat()
        else:
            # Chuyển đổi thành chuỗi
            value_str = str(value)

        # Thêm kiểu dữ liệu nếu cần
        if self.include_types:
            value_str = f"{type(value).__name__}:{value_str}"

        self.parts.append(value_str)
        return self

    def add_dict(self, d: Dict[str, Any]) -> "CacheKeyBuilder":
        """
        Thêm dictionary vào cache key.

        Args:
            d: Dictionary cần thêm

        Returns:
            Self reference cho method chaining
        """
        # Sắp xếp key
        sorted_items = sorted(d.items())

        # Tạo chuỗi key-value
        kv_parts = []
        for key, value in sorted_items:
            if isinstance(value, (dict, list, tuple, set)):
                # Hash cho các cấu trúc dữ liệu phức tạp
                value_str = hashlib.md5(
                    json.dumps(value, sort_keys=True, default=str).encode()
                ).hexdigest()
            elif isinstance(value, datetime):
                # Format datetime
                value_str = value.isoformat()
            else:
                # Chuyển đổi thành chuỗi
                value_str = str(value)

            kv_parts.append(f"{key}:{value_str}")

        # Tạo chuỗi từ các phần
        dict_str = "_".join(kv_parts)

        # Hash nếu quá dài
        if len(dict_str) > 100:
            dict_str = hashlib.md5(dict_str.encode()).hexdigest()

        self.parts.append(dict_str)
        return self

    def add_suffix(self, suffix: str) -> "CacheKeyBuilder":
        """
        Thêm hậu tố vào cache key.

        Args:
            suffix: Hậu tố cần thêm

        Returns:
            Self reference cho method chaining
        """
        self.parts.append(str(suffix))
        return self

    def build(self) -> str:
        """
        Xây dựng cache key từ các phần.

        Returns:
            Cache key
        """
        # Tạo key từ các phần
        key = ":".join(self.parts)

        # Nếu key quá dài (> 200 ký tự), hash để rút gọn
        if len(key) > 200:
            # Giữ prefix và namespace
            prefix_parts = []
            if self.prefix:
                prefix_parts.append(self.prefix)
            if self.namespace:
                prefix_parts.append(self.namespace)

            prefix_str = ":".join(prefix_parts) + ":" if prefix_parts else ""

            # Hash phần còn lại
            hash_part = hashlib.md5(key.encode()).hexdigest()

            # Tạo key mới
            key = f"{prefix_str}{hash_part}"

        return key


def generate_cache_key(
    *args,
    prefix: Optional[str] = None,
    namespace: Optional[str] = None,
    suffix: Optional[str] = None,
    include_args_types: bool = False,
) -> str:
    """
    Tạo cache key từ tham số.

    Args:
        *args: Các tham số sử dụng để tạo key
        prefix: Tiền tố key
        namespace: Namespace cho key
        suffix: Hậu tố key
        include_args_types: Bao gồm kiểu dữ liệu trong key

    Returns:
        Cache key
    """
    # Tạo danh sách các giá trị chuỗi
    parts = []

    # Thêm prefix
    if prefix:
        parts.append(str(prefix))

    # Thêm namespace
    if namespace:
        parts.append(str(namespace))

    # Thêm các tham số
    for i, arg in enumerate(args):
        # Chuyển đổi arg thành chuỗi
        if isinstance(arg, (dict, list, tuple, set)):
            # Hash cho các cấu trúc dữ liệu phức tạp
            arg_str = hashlib.md5(json.dumps(arg, sort_keys=True).encode()).hexdigest()
        elif isinstance(arg, datetime):
            # Format datetime
            arg_str = arg.isoformat()
        else:
            # Chuyển đổi thành chuỗi
            arg_str = str(arg)

        # Thêm kiểu dữ liệu nếu cần
        if include_args_types:
            arg_str = f"{type(arg).__name__}:{arg_str}"

        parts.append(arg_str)

    # Thêm suffix
    if suffix:
        parts.append(str(suffix))

    # Tạo key từ các phần
    key = ":".join(parts)

    # Nếu key quá dài (> 200 ký tự), hash để rút gọn
    if len(key) > 200:
        # Giữ prefix và namespace
        prefix_parts = []
        if prefix:
            prefix_parts.append(prefix)
        if namespace:
            prefix_parts.append(namespace)

        prefix_str = ":".join(prefix_parts) + ":" if prefix_parts else ""

        # Hash phần còn lại
        hash_part = hashlib.md5(key.encode()).hexdigest()

        # Tạo key mới
        key = f"{prefix_str}{hash_part}"

    return key


def create_model_key(
    model_name: str,
    obj_id: Union[int, str],
    prefix: Optional[str] = None,
    suffix: Optional[str] = None,
) -> str:
    """
    Tạo cache key cho model object.

    Args:
        model_name: Tên model
        obj_id: ID đối tượng
        prefix: Tiền tố key
        suffix: Hậu tố key

    Returns:
        Cache key
    """
    # Tạo key
    parts = []

    # Thêm prefix
    if prefix:
        parts.append(str(prefix))

    # Thêm model_name
    parts.append(model_name.lower())

    # Thêm obj_id
    parts.append(str(obj_id))

    # Thêm suffix
    if suffix:
        parts.append(str(suffix))

    # Tạo key từ các phần
    return ":".join(parts)


def create_list_key(
    model_name: str,
    filter_params: Optional[Dict[str, Any]] = None,
    prefix: Optional[str] = None,
    suffix: Optional[str] = None,
) -> str:
    """
    Tạo cache key cho danh sách objects.

    Args:
        model_name: Tên model
        filter_params: Tham số lọc
        prefix: Tiền tố key
        suffix: Hậu tố key

    Returns:
        Cache key
    """
    # Tạo key
    parts = []

    # Thêm prefix
    if prefix:
        parts.append(str(prefix))

    # Thêm model_name
    parts.append(f"{model_name.lower()}s")

    # Thêm filter_params
    if filter_params:
        # Sắp xếp tham số để tạo key nhất quán
        sorted_params = sorted(filter_params.items())

        # Tạo chuỗi tham số
        params_str = "_".join(f"{k}:{v}" for k, v in sorted_params)

        # Hash nếu quá dài
        if len(params_str) > 100:
            params_str = hashlib.md5(params_str.encode()).hexdigest()

        parts.append(params_str)

    # Thêm suffix
    if suffix:
        parts.append(str(suffix))

    # Tạo key từ các phần
    return ":".join(parts)


def create_query_key(
    query: str,
    params: Optional[Dict[str, Any]] = None,
    prefix: Optional[str] = None,
    suffix: Optional[str] = None,
) -> str:
    """
    Tạo cache key cho truy vấn SQL.

    Args:
        query: Câu truy vấn SQL
        params: Tham số truy vấn
        prefix: Tiền tố key
        suffix: Hậu tố key

    Returns:
        Cache key
    """
    # Tạo key
    parts = []

    # Thêm prefix
    if prefix:
        parts.append(str(prefix))

    # Chuẩn hóa câu truy vấn
    # Loại bỏ khoảng trắng và xuống dòng
    normalized_query = re.sub(r"\s+", " ", query).strip()

    # Hash câu truy vấn
    query_hash = hashlib.md5(normalized_query.encode()).hexdigest()
    parts.append(f"query:{query_hash}")

    # Thêm tham số
    if params:
        # Sắp xếp tham số
        sorted_params = sorted(params.items())

        # Tạo chuỗi tham số
        params_str = "_".join(f"{k}:{v}" for k, v in sorted_params)

        # Hash nếu quá dài
        if len(params_str) > 100:
            params_str = hashlib.md5(params_str.encode()).hexdigest()

        parts.append(f"params:{params_str}")

    # Thêm suffix
    if suffix:
        parts.append(str(suffix))

    # Tạo key từ các phần
    return ":".join(parts)


def create_api_response_key(
    path: str,
    query_params: Optional[Dict[str, str]] = None,
    headers: Optional[Dict[str, str]] = None,
    user_id: Optional[Union[int, str]] = None,
    prefix: Optional[str] = None,
) -> str:
    """
    Tạo cache key cho API response.

    Args:
        path: Đường dẫn API
        query_params: Query parameters
        headers: Headers ảnh hưởng đến response
        user_id: ID người dùng
        prefix: Tiền tố key

    Returns:
        Cache key
    """
    # Tạo key
    parts = []

    # Thêm prefix
    if prefix:
        parts.append(str(prefix))

    # Thêm normalized path
    normalized_path = path.rstrip("/").lower()
    parts.append(normalized_path)

    # Thêm user_id nếu có
    if user_id:
        parts.append(f"user:{user_id}")

    # Thêm query params
    if query_params:
        # Sắp xếp tham số
        sorted_params = sorted(query_params.items())

        # Tạo chuỗi tham số
        params_str = "_".join(f"{k}:{v}" for k, v in sorted_params)

        # Hash nếu quá dài
        if len(params_str) > 100:
            params_str = hashlib.md5(params_str.encode()).hexdigest()

        parts.append(f"params:{params_str}")

    # Thêm headers quan trọng
    if headers:
        # Lọc headers quan trọng
        important_headers = {
            k.lower(): v
            for k, v in headers.items()
            if k.lower() in ["accept", "accept-language", "content-type"]
        }

        if important_headers:
            # Sắp xếp headers
            sorted_headers = sorted(important_headers.items())

            # Tạo chuỗi headers
            headers_str = "_".join(f"{k}:{v}" for k, v in sorted_headers)

            # Hash nếu quá dài
            if len(headers_str) > 100:
                headers_str = hashlib.md5(headers_str.encode()).hexdigest()

            parts.append(f"headers:{headers_str}")

    # Tạo key từ các phần
    return ":".join(parts)
