"""Kiểm tra URL camera trước khi lưu hoặc mở; không thực hiện kết nối mạng."""

from urllib.parse import urlsplit, urlunsplit


# --------------------------- Kiểm tra URL camera -----------------------------
def validate_rtsp_url(value: str) -> str:
    """Nhận RTSP/RTSPS có host/port hợp lệ, từ chối ký tự điều khiển và fragment.

    Trả URL gốc đã bỏ khoảng trắng hai đầu, giữ nguyên credentials/path/query.
    ValueError chỉ chứa thông báo chung, không đưa URL bí mật vào exception.
    """
    if not isinstance(value, str):
        raise ValueError("URL RTSP không hợp lệ.")
    value = value.strip()
    if (
        not value
        or len(value) > 2048
        or any(ord(char) <= 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError("URL RTSP không hợp lệ.")
    try:
        parsed = urlsplit(value)
        port = parsed.port
        valid = (
            parsed.scheme.lower() in {"rtsp", "rtsps"}
            and parsed.hostname
            and not parsed.fragment
        )
        if not valid or (port is not None and not 1 <= port <= 65535):
            raise ValueError
    except ValueError:
        raise ValueError("URL RTSP không hợp lệ.") from None
    return value


# ----------------------------- Nhãn URL camera -------------------------------
def rtsp_label(value: str) -> str:
    """Che toàn bộ credentials và query khi tạo response/log; không đổi URL lưu thật."""
    # Bản ghi stream cũ có thể dùng HTTP/RTMP; response vẫn phải che được URL.
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "[STREAM]"
    if not parsed.hostname:
        return "[STREAM]"
    return urlunsplit(
        (parsed.scheme, parsed.netloc.rsplit("@", 1)[-1], parsed.path, "", "")
    )
