"""Chuẩn hoá URL YouTube trước khi gọi resolver, không nhận URL media tuỳ ý."""

import re
from urllib.parse import parse_qs, urlsplit


# ------------------------- Chuẩn hoá liên kết YouTube -------------------------
def normalize_youtube_url(value: str) -> str:
    """Trả URL watch canonical cho một video, loại query theo dõi/playlist.

    Tham số:
        value: URL watch, youtu.be, shorts, live hoặc embed từ người dùng.
    Trả về:
        URL HTTPS chỉ gồm video ID, không có token hay tham số phụ.
    Ngoại lệ:
        ValueError: URL không thuộc YouTube hoặc thiếu video ID 11 ký tự.
    """
    try:
        parsed = urlsplit(value.strip())
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
            or any(ord(char) <= 32 for char in value.strip())
        ):
            raise ValueError
        if parsed.hostname == "youtu.be":
            video_id = parsed.path.removeprefix("/")
        elif parsed.hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            parts = parsed.path.strip("/").split("/")
            if parsed.path == "/watch":
                ids = parse_qs(parsed.query).get("v", [])
                video_id = ids[0] if len(ids) == 1 else ""
            elif len(parts) == 2 and parts[0] in {"shorts", "live", "embed"}:
                video_id = parts[1]
            else:
                raise ValueError
        else:
            raise ValueError
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id) is None:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("Nhập liên kết của một video YouTube hợp lệ.") from None
    return f"https://www.youtube.com/watch?v={video_id}"
