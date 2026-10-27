"""Tải encoder chính thức cho YOLOE ở bước setup, độc lập với inference offline."""

import argparse
import os
import urllib.request

from app.adapters.ultralytics.yoloe import ENCODERS, encoder_directory


# -------------------------- Chuẩn bị encoder YOLOE ---------------------------
def main() -> None:
    """Nhận --series 26/11/all và tải encoder còn thiếu vào storage local.

    Tác động phụ: tải asset Ultralytics qua HTTPS, ghi file tạm rồi thay thế nguyên
    tử; không ghi model thư viện hay DB. Lỗi mạng được trả ra terminal để thử lại.
    """
    parser = argparse.ArgumentParser(description="Chuẩn bị text encoder YOLOE")
    parser.add_argument("--series", choices=("26", "11", "all"), default="26")
    args = parser.parse_args()
    directory = encoder_directory()
    directory.mkdir(parents=True, exist_ok=True)
    variants = {
        "26": ["mobileclip2:b"],
        "11": ["mobileclip:blt"],
        "all": list(ENCODERS),
    }
    for variant in variants[args.series]:
        filename = ENCODERS[variant]
        destination = directory / filename
        if destination.is_file():
            print(f"Đã có: {destination}")
            continue
        temporary = directory / f".{filename}.{os.getpid()}.download"
        try:
            url = f"https://github.com/ultralytics/assets/releases/download/v8.4.0/{filename}"
            print(f"Đang tải {filename}…", flush=True)
            with (
                urllib.request.urlopen(url, timeout=60) as response,
                temporary.open("wb") as output,
            ):
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            temporary.replace(destination)
            print(f"Đã lưu: {destination}")
        finally:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
