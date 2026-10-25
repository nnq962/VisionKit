"""Đọc metadata và tạo preview cho ảnh thường lẫn ảnh HEIC/HEIF của iPhone."""

import warnings
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from app.core.errors import SourceError

register_heif_opener()

FORMATS = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "WEBP": ("webp", "image/webp"),
    "GIF": ("gif", "image/gif"),
    "BMP": ("bmp", "image/bmp"),
    "AVIF": ("avif", "image/avif"),
    "HEIF": ("heic", "image/heic"),
}


# ------------------------ Đọc metadata và tạo preview ------------------------
def inspect_image(
    path: Path, max_pixels: int, make_preview: bool = False
) -> tuple[dict[str, Any], bytes | None]:
    """Xác minh ảnh, đọc kích thước hiển thị và tạo JPEG preview khi cần.

    Tham số:
        path: File upload tạm cần đọc, không bị chỉnh sửa bởi hàm này.
        max_pixels: Giới hạn tổng số pixel trước khi giải mã.
        make_preview: Tạo JPEG cho mọi định dạng; HEIF luôn tạo preview.
    Trả về:
        Metadata và JPEG bytes tuỳ chọn. Preview tối đa 2048px, đã áp dụng
        EXIF/HEIF orientation; file gốc vẫn giữ nguyên, kể cả dữ liệu HDR.
    Ngoại lệ:
        SourceError: 413 khi ảnh quá lớn, 415 khi không giải mã được ảnh.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path, formats=list(FORMATS)) as image:
                if image.width * image.height > max_pixels:
                    raise SourceError(
                        413, f"Ảnh vượt giới hạn {max_pixels // 1_000_000} triệu pixel."
                    )
                image_format = image.format
                image.verify()
            with Image.open(path, formats=list(FORMATS)) as image:
                image.load()
                # Plugin HEIF xử lý irot/imir; EXIF transpose tránh xoay lại hai lần.
                ImageOps.exif_transpose(image, in_place=True)
                metadata = {
                    "width": image.width,
                    "height": image.height,
                    "format": "HEIC" if image_format == "HEIF" else image_format,
                    "mime_type": FORMATS[image_format][1],
                    "extension": FORMATS[image_format][0],
                }
                preview = None
                if make_preview or image_format == "HEIF":
                    icc_profile = image.info.get("icc_profile")
                    image.thumbnail((2048, 2048))
                    rgba = image.convert("RGBA")
                    rgb = Image.new("RGB", rgba.size, "white")
                    rgb.paste(rgba, mask=rgba.getchannel("A"))
                    output = BytesIO()
                    rgb.save(output, format="JPEG", quality=88, icc_profile=icc_profile)
                    preview = output.getvalue()
                return metadata, preview
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
        RuntimeError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise SourceError(
            415,
            "Không đọc được ảnh. Hỗ trợ JPG, PNG, WebP, GIF, BMP, AVIF và HEIC/HEIF hợp lệ.",
        ) from error
