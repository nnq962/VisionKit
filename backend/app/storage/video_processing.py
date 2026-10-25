"""Đọc metadata video và tạo thumbnail; không xử lý inference."""

import json
import math
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

from app.core.errors import SourceError


# ------------------------- Chạy công cụ xử lý video --------------------------
def run_video_tool(arguments: list[str]) -> bytes:
    """Chạy lệnh FFmpeg/ffprobe không qua shell và trả stdout dạng bytes.

    Tham số:
        arguments: Tên chương trình và các tham số riêng biệt, chỉ đọc file local.
    Ngoại lệ:
        SourceError: 503 nếu thiếu công cụ, 415 nếu lỗi hoặc quá 30 giây.
    Tác động phụ:
        Tạo tiến trình con, tự kết thúc khi hết thời gian xử lý.
    """
    try:
        return subprocess.run(
            arguments, check=True, capture_output=True, timeout=30
        ).stdout
    except FileNotFoundError as error:
        raise SourceError(
            503, "Backend cần cài FFmpeg và ffprobe để lưu video."
        ) from error
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise SourceError(
            415, "Không đọc được video. Tệp có thể hỏng hoặc không được hỗ trợ."
        ) from error


# --------------------------- Phân tích file video ----------------------------
def inspect_video(path: Path) -> tuple[dict[str, Any], bytes]:
    """Xác minh container, lấy metadata và giải mã một frame thành JPEG.

    Tham số:
        path: File upload tạm trên máy backend.
    Trả về:
        Metadata gồm kích thước hiển thị, thời lượng, FPS, codec và JPEG thumbnail.
    Ngoại lệ:
        SourceError: 415 khi file không có video hợp lệ; 503 khi thiếu công cụ.
    Tác động phụ:
        Chạy ffprobe và FFmpeg với giới hạn thời gian, không chuyển mã video gốc.
    """
    raw = run_video_tool(
        [
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-format_whitelist",
            "mov,matroska,webm,ogg",
            "-select_streams",
            "V:0",
            "-show_entries",
            "format=format_name,duration:format_tags=major_brand:stream=width,height,codec_name,avg_frame_rate,duration:stream_side_data=rotation",
            "-of",
            "json",
            str(path),
        ]
    )
    try:
        data = json.loads(raw)
        stream = data["streams"][0]
        container = data["format"]
        formats = container["format_name"].split(",")
        if "mov" in formats:
            is_mov = container.get("tags", {}).get("major_brand", "").strip() == "qt"
            extension, mime = (
                ("mov", "video/quicktime") if is_mov else ("mp4", "video/mp4")
            )
        elif "webm" in formats:
            with path.open("rb") as file:
                header = file.read(4096)
            if b"webm" not in header:
                raise ValueError("Chỉ hỗ trợ WebM trong nhóm Matroska")
            extension, mime = "webm", "video/webm"
        elif "ogg" in formats:
            extension, mime = "ogv", "video/ogg"
        else:
            raise ValueError("container")
        width, height = int(stream["width"]), int(stream["height"])
        duration = float(container.get("duration", stream.get("duration", 0)))
        if min(width, height) <= 0 or not math.isfinite(duration) or duration <= 0:
            raise ValueError("metadata")
        rotation = next(
            (
                float(item["rotation"])
                for item in stream.get("side_data_list", [])
                if "rotation" in item
            ),
            0,
        )
        if abs(rotation) % 180 == 90:
            width, height = height, width
        metadata = dict(
            width=width,
            height=height,
            duration=duration,
            codec=stream.get("codec_name"),
            format=extension.upper(),
            extension=extension,
            mime_type=mime,
        )
        try:
            fps = float(Fraction(stream.get("avg_frame_rate", "0/1")))
            if math.isfinite(fps) and fps > 0:
                metadata["fps"] = round(fps, 3)
        except (ValueError, ZeroDivisionError):
            pass
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise SourceError(
            415, "Tệp không có video hợp lệ hoặc thiếu thời lượng."
        ) from error
    preview = run_video_tool(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-threads",
            "1",
            "-protocol_whitelist",
            "file,pipe",
            "-format_whitelist",
            "mov,matroska,webm,ogg",
            "-i",
            str(path),
            "-map",
            "0:V:0",
            "-frames:v",
            "1",
            "-an",
            "-vf",
            "scale=640:640:force_original_aspect_ratio=decrease",
            "-threads",
            "1",
            "-f",
            "image2pipe",
            "-c:v",
            "mjpeg",
            "pipe:1",
        ]
    )
    if not preview:
        raise SourceError(415, "Không tạo được thumbnail video.")
    return metadata, preview
