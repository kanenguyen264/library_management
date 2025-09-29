import json
import pickle
import base64
from typing import Any, Dict, List, Optional, Union, Set, Tuple
from app.logging.setup import get_logger
from datetime import datetime, date, time
from enum import Enum
from decimal import Decimal
import dataclasses
import uuid

logger = get_logger(__name__)


class SerializationFormat(str, Enum):
    """Các định dạng serialize."""

    JSON = "json"
    PICKLE = "pickle"
    AUTO = "auto"


def serialize_data(
    data: Any, format: SerializationFormat = SerializationFormat.AUTO
) -> Union[str, bytes]:
    """
    Serialize dữ liệu để lưu vào cache.

    Args:
        data: Dữ liệu cần serialize
        format: Định dạng serialize

    Returns:
        Dữ liệu đã serialize (string hoặc bytes)
    """
    try:
        # Xác định format
        actual_format = format
        if format == SerializationFormat.AUTO:
            if is_json_serializable(data):
                actual_format = SerializationFormat.JSON
            else:
                actual_format = SerializationFormat.PICKLE

        # Serialize theo format
        if actual_format == SerializationFormat.JSON:
            return json.dumps(data, cls=EnhancedJSONEncoder)
        elif actual_format == SerializationFormat.PICKLE:
            serialized = pickle.dumps(data)
            # Encode binary to string for storage
            return base64.b64encode(serialized)
        else:
            raise ValueError(f"Định dạng serialize không hỗ trợ: {format}")

    except Exception as e:
        logger.error(f"Lỗi khi serialize dữ liệu: {str(e)}")
        raise


def deserialize_data(data: Union[str, bytes]) -> Any:
    """
    Deserialize dữ liệu từ cache.

    Args:
        data: Dữ liệu đã serialize

    Returns:
        Dữ liệu gốc
    """
    if data is None:
        return None

    try:
        # Xác định định dạng dữ liệu
        if isinstance(data, bytes):
            try:
                # Thử giải mã JSON
                return json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                # Có thể là Pickle
                try:
                    return pickle.loads(data)
                except:
                    # Dữ liệu pickled được base64 encode
                    try:
                        decoded = base64.b64decode(data)
                        return pickle.loads(decoded)
                    except:
                        # Không thể deserialize
                        logger.error("Không thể deserialize dữ liệu binary")
                        return data
        elif isinstance(data, str):
            try:
                # Thử giải mã JSON
                return json.loads(data)
            except json.JSONDecodeError:
                # Có thể là Pickle được base64 encode
                try:
                    decoded = base64.b64decode(data)
                    return pickle.loads(decoded)
                except:
                    # Không thể deserialize
                    return data
        else:
            # Không phải string hoặc bytes
            return data

    except Exception as e:
        logger.error(f"Lỗi khi deserialize dữ liệu: {str(e)}")
        return data


# Tạo hàm adapter cho các backend đã import serialize, deserialize
def serialize(data: Any, format_name: str = "json") -> Union[str, bytes]:
    """
    Adapter function để duy trì tương thích ngược với các backend.

    Args:
        data: Dữ liệu cần serialize
        format_name: Tên định dạng

    Returns:
        Dữ liệu đã serialize
    """
    format_map = {
        "json": SerializationFormat.JSON,
        "pickle": SerializationFormat.PICKLE,
    }
    format_enum = format_map.get(format_name, SerializationFormat.AUTO)
    return serialize_data(data, format_enum)


def deserialize(
    data: Union[str, bytes], format_name: str = "json", allow_pickle: bool = False
) -> Any:
    """
    Adapter function để duy trì tương thích ngược với các backend.

    Args:
        data: Dữ liệu đã serialize
        format_name: Tên định dạng
        allow_pickle: Cho phép sử dụng pickle

    Returns:
        Dữ liệu gốc
    """
    return deserialize_data(data)


def is_json_serializable(data: Any) -> bool:
    """
    Kiểm tra xem dữ liệu có thể serialize bằng JSON không.

    Args:
        data: Dữ liệu cần kiểm tra

    Returns:
        True nếu có thể serialize bằng JSON
    """
    try:
        json.dumps(data, cls=EnhancedJSONEncoder)
        return True
    except (TypeError, OverflowError):
        return False


class EnhancedJSONEncoder(json.JSONEncoder):
    """JSON Encoder hỗ trợ thêm các kiểu dữ liệu của Python."""

    def default(self, obj):
        # Xử lý datetime
        if isinstance(obj, (datetime, date, time)):
            return obj.isoformat()

        # Xử lý Decimal
        elif isinstance(obj, Decimal):
            return float(obj)

        # Xử lý UUID
        elif isinstance(obj, uuid.UUID):
            return str(obj)

        # Xử lý Enum
        elif isinstance(obj, Enum):
            return obj.value

        # Xử lý dataclasses
        elif dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)

        # Xử lý các đối tượng có phương thức to_dict
        elif hasattr(obj, "to_dict") and callable(getattr(obj, "to_dict")):
            return obj.to_dict()

        # Xử lý các đối tượng có phương thức __dict__
        elif hasattr(obj, "__dict__"):
            return obj.__dict__

        # Xử lý set
        elif isinstance(obj, set):
            return list(obj)

        # Gọi phương thức mặc định cho các kiểu khác
        return super().default(obj)
