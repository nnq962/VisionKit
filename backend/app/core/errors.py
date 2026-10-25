"""Lỗi nghiệp vụ được chuyển thành HTTP response tại lớp API."""


# --------------------------- Lỗi nghiệp vụ source ----------------------------
class SourceError(Exception):
    """Biểu diễn lỗi source có mã HTTP và thông báo tiếng Việt cho người dùng.

    Thuộc tính:
        status_code: Mã HTTP phù hợp với lỗi nghiệp vụ.
        message: Thông báo có thể hiển thị trên giao diện.
    """

    def __init__(self, status_code: int, message: str) -> None:
        """Khởi tạo lỗi với mã HTTP và thông báo; không ghi dữ liệu."""
        super().__init__(message)
        self.status_code = status_code
        self.message = message
