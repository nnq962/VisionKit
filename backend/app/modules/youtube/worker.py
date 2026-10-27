"""Worker yt-dlp riêng để timeout/cancel thu hồi cả download lẫn tiến trình con."""

import json
import shutil
import sys
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.core.youtube import normalize_youtube_url


# ------------------------ Chuẩn bị video trong worker -------------------------
def prepare_video(payload: dict) -> dict:
    """Tải tối đa 720p H264, chặn live/dung lượng, trả metadata không có signed URL.

    Nhận URL, thư mục riêng và giới hạn byte từ service nội bộ. Tác động phụ:
    tạo file trong thư mục job. DownloadError báo video không hỗ trợ hoặc quá lớn.
    Service cha chịu trách nhiệm timeout, kill và xoá toàn bộ thư mục khi lỗi.
    """
    url = normalize_youtube_url(payload["url"])
    root = Path(payload["root"])
    limit = payload["limit"]

    def bounded_download(progress: dict) -> None:
        """Dừng cả stream không biết Content-Length khi số byte vượt hạn."""
        if progress.get("downloaded_bytes", 0) > limit:
            raise DownloadError("Video vượt giới hạn dung lượng.")

    def finite_video(info: dict, *, incomplete: bool) -> str | None:
        """Chặn live, video lên lịch và thời lượng quá bốn giờ trước khi tải."""
        if info.get("is_live") or info.get("live_status") in {
            "is_live",
            "is_upcoming",
            "post_live",
        }:
            return "Nguồn trực tiếp chưa hỗ trợ ở luồng video thường."
        if (info.get("duration") or 0) > 14400:
            return "Video dài hơn bốn giờ."
        return None

    options = {
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 10,
        "retries": 1,
        "fragment_retries": 1,
        "extractor_retries": 1,
        "max_filesize": limit,
        "format": "best[ext=mp4][vcodec^=avc1][height<=720]/bestvideo[ext=mp4][vcodec^=avc1][height<=720]",
        "outtmpl": str(root / "video.%(ext)s"),
        "progress_hooks": [bounded_download],
        "match_filter": finite_video,
        "js_runtimes": {"node": {"path": shutil.which("node")}}
        if shutil.which("node")
        else {},
    }
    with YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=False)
        if info and (
            info.get("is_live")
            or info.get("live_status") in {"is_live", "is_upcoming", "post_live"}
        ):
            raise ValueError("live")
        if info and (info.get("duration") or 0) > 14400:
            raise ValueError("duration")
        if not info:
            raise DownloadError("Không tìm thấy video.")
        downloader.process_ie_result(info, download=True)
    path = root / "video.mp4"
    if not info or not path.is_file() or not 0 < path.stat().st_size <= limit:
        raise DownloadError("Không có file video trong giới hạn.")
    return {"title": str(info.get("title") or "YouTube")[:120], "video_id": info["id"]}


# ------------------------------ Điểm vào worker ------------------------------
def main() -> None:
    """Đọc stdin giới hạn, chỉ xuất JSON tóm tắt; stderr do service cha ẩn."""
    payload = json.loads(sys.stdin.buffer.read(16384))
    try:
        result = prepare_video(payload)
    except ValueError as error:
        messages = {
            "live": "Đây là YouTube Live hoặc video lên lịch. Hiện hãy chọn video đã phát xong.",
            "duration": "Video dài hơn giới hạn bốn giờ.",
        }
        result = {"error": messages.get(str(error), "Liên kết video không hợp lệ.")}
    except Exception:
        result = {
            "error": "Không tải được video. Video cần công khai, có MP4 H.264 và trong giới hạn dung lượng. YouTube có thể tạm chặn truy cập; hãy thử lại sau."
        }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
