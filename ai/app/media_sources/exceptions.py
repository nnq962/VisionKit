"""Ngoại lệ chung cho reader và việc thu hồi tài nguyên."""


# --------------------------- Đọc và quản lý source ---------------------------
class MediaSourceError(ValueError):
    """Nguồn không hợp lệ hoặc không đọc được; tương thích lỗi worker hiện có."""


# --------------------------- Đọc và quản lý source ---------------------------
class StreamError(MediaSourceError):
    """Stream lỗi hoặc thread chưa dừng; bên gọi không được mở lại reader."""
