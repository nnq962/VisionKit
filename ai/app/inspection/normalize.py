"""Chuẩn hoá metadata đọc từ các định dạng model mà không tự đoán tên file."""

import ast
import json
from typing import Any


# --------------------------- Đọc giá trị metadata ----------------------------
def literal(value: Any) -> Any:
    """Đọc JSON/literal Python tối đa 256 KiB; trả nguyên giá trị nếu không phân tích được.

    Không dùng eval; dùng cho names/imgsz được Ultralytics ghi vào ONNX dưới dạng chuỗi.
    """
    if not isinstance(value, str) or len(value) > 262144:
        return value
    for parser in (json.loads, ast.literal_eval):
        try:
            return parser(value)
        except (ValueError, SyntaxError, TypeError, RecursionError):
            continue
    return value


# ---------------------------- Chuẩn hoá tên class ----------------------------
def class_names(value: Any) -> dict[str, str]:
    """Trả tối đa 10.000 tên class dạng map ID chuỗi; bỏ qua key/label không hợp lệ."""
    value = literal(value)
    if isinstance(value, list):
        value = dict(enumerate(value))
    if not isinstance(value, dict):
        return {}
    return {
        str(key): str(label)[:200]
        for key, label in list(value.items())[:10000]
        if str(key).isdigit() and isinstance(label, str)
    }


# --------------------------- Chuẩn hoá kích thước ----------------------------
def image_size(value: Any) -> list[int] | None:
    """Đổi imgsz nguyên hoặc cặp [h,w] thành hai số dương; trả None nếu thiếu hoặc sai."""
    value = literal(value)
    if isinstance(value, int):
        value = [value, value]
    if (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(isinstance(item, int) and 0 < item <= 32768 for item in value)
    ):
        return list(value)
    return None
