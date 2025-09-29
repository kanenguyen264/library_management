import html
import re
from typing import Any, Dict, List, Union
import bleach
from urllib.parse import urlparse, urlencode, parse_qsl


def sanitize_html(value: str) -> str:
    """
    Làm sạch HTML đầu vào, loại bỏ các thẻ và thuộc tính nguy hiểm.

    Args:
        value: Chuỗi HTML cần làm sạch

    Returns:
        Chuỗi HTML đã được làm sạch
    """
    allowed_tags = [
        "a",
        "abbr",
        "acronym",
        "b",
        "blockquote",
        "br",
        "code",
        "div",
        "em",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "i",
        "li",
        "ol",
        "p",
        "pre",
        "span",
        "strong",
        "table",
        "tbody",
        "td",
        "th",
        "thead",
        "tr",
        "ul",
    ]

    allowed_attrs = {
        "a": ["href", "title", "target"],
        "abbr": ["title"],
        "acronym": ["title"],
        "*": ["class", "id"],
    }

    return bleach.clean(value, tags=allowed_tags, attributes=allowed_attrs, strip=True)


def sanitize_text(value: str) -> str:
    """
    Làm sạch text đầu vào, chuyển các ký tự HTML đặc biệt thành entities.

    Args:
        value: Chuỗi cần làm sạch

    Returns:
        Chuỗi đã được làm sạch
    """
    return html.escape(value)


def sanitize_sql(value: str) -> str:
    """
    Làm sạch chuỗi đầu vào để ngăn SQL injection.
    Lưu ý: Đây chỉ là một lớp bảo vệ thêm, không thay thế prepared statements.

    Args:
        value: Chuỗi cần làm sạch

    Returns:
        Chuỗi đã được làm sạch
    """
    # Loại bỏ các ký tự có thể gây SQL injection
    return re.sub(r"['\"\\;%_\*]", "", value)


def sanitize_filename(value: str) -> str:
    """
    Làm sạch tên file để ngăn path traversal.

    Args:
        value: Tên file cần làm sạch

    Returns:
        Tên file đã được làm sạch
    """
    # Loại bỏ đường dẫn, giữ lại chỉ tên file
    value = re.sub(r"[\\/]", "", value)

    # Loại bỏ các ký tự nguy hiểm
    value = re.sub(r"[^\w\.\-]", "_", value)

    # Đảm bảo không có chuỗi '..' trong tên file
    value = value.replace("..", "_")

    return value


def sanitize_url(value: str) -> str:
    """
    Làm sạch URL để ngăn open redirect và XSS.

    Args:
        value: URL cần làm sạch

    Returns:
        URL đã được làm sạch hoặc '#' nếu không an toàn
    """
    # Kiểm tra URL hợp lệ
    try:
        parsed = urlparse(value)
        # Chỉ cho phép http và https
        if parsed.scheme not in ("http", "https"):
            return "#"

        # Xử lý các ký tự đặc biệt trong query string
        if parsed.query:
            query_dict = dict(parse_qsl(parsed.query))
            sanitized_query = urlencode(query_dict)

            # Tái tạo URL với query string đã làm sạch
            from urllib.parse import urlunparse

            value = urlunparse(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    parsed.params,
                    sanitized_query,
                    parsed.fragment,
                )
            )

        return value
    except Exception:
        return "#"


def sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Làm sạch tất cả chuỗi trong dict.

    Args:
        data: Dict cần làm sạch

    Returns:
        Dict đã được làm sạch
    """
    result = {}
    for key, value in data.items():
        if isinstance(value, str):
            # Làm sạch chuỗi
            result[key] = sanitize_text(value)
        elif isinstance(value, dict):
            # Đệ quy cho dict con
            result[key] = sanitize_dict(value)
        elif isinstance(value, list):
            # Làm sạch list
            result[key] = sanitize_list(value)
        else:
            # Giữ nguyên giá trị khác
            result[key] = value

    return result


def sanitize_list(data: List[Any]) -> List[Any]:
    """
    Làm sạch tất cả chuỗi trong list.

    Args:
        data: List cần làm sạch

    Returns:
        List đã được làm sạch
    """
    result = []
    for item in data:
        if isinstance(item, str):
            result.append(sanitize_text(item))
        elif isinstance(item, dict):
            result.append(sanitize_dict(item))
        elif isinstance(item, list):
            result.append(sanitize_list(item))
        else:
            result.append(item)

    return result


def sanitize_search_query(query: str) -> str:
    """
    Làm sạch truy vấn tìm kiếm để ngăn ngừa các tấn công injection và xss.

    Args:
        query: Chuỗi truy vấn tìm kiếm cần làm sạch

    Returns:
        Chuỗi truy vấn đã được làm sạch
    """
    # Loại bỏ các ký tự nguy hiểm
    query = re.sub(r"[<>{}[\]\\]", "", query)

    # Loại bỏ các chuỗi có thể gây SQL injection
    query = re.sub(
        r"(UNION|SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)\s",
        "",
        query,
        flags=re.IGNORECASE,
    )

    # Giới hạn độ dài truy vấn
    max_length = 200
    if len(query) > max_length:
        query = query[:max_length]

    return query.strip()
