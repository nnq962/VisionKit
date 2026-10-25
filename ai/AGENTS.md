# AI conventions

## Phạm vi

- Module AI dùng Python 3.10, quản lý môi trường và dependency bằng uv.
- AI phụ trách đọc metadata, load model và inference qua API nội bộ. Backend quản lý DB, upload và file; AI không truy cập SQLite.

## Phong cách Python

- Viết code rõ ràng, dễ hiểu; ưu tiên cách viết trực tiếp thay vì biểu thức ngắn nhưng khó đọc.
- Đặt tên biến, hàm và class mô tả đúng mục đích. Hàm nên tập trung vào một trách nhiệm.
- Thêm type hint cho tham số và giá trị trả về. Mọi hàm, method (kể cả `__init__`) và class đều phải có docstring tiếng Việt.
- Comment giải thích ý định hoặc lý do của logic; không lặp lại điều code đã thể hiện rõ.

## Comment phân cách

- Trước mỗi hàm cấp module và mỗi class, thêm một dòng comment phân cách có tên hoặc mô tả ngắn. Giữ hai dòng trống giữa các định nghĩa theo PEP 8.
- Nếu hàm hoặc class có decorator, đặt comment phân cách phía trên toàn bộ decorator.
- Không cần thêm dòng phân cách giữa các method trong cùng một class; nhóm logic bằng khoảng trắng và docstring khi phù hợp.
- Mọi dòng comment phân cách có tổng độ dài đúng **79 ký tự**, tính cả `#`, khoảng trắng và dấu `-`, không tính ký tự xuống dòng hoặc phần thụt lề.
- Dùng định dạng `# --- Mô tả ---`: tiêu đề ngắn bằng tiếng Việt ở giữa, bù dấu `-` hai bên để đủ 79 ký tự. Hai bên chênh lệch tối đa một dấu `-`; nếu tiêu đề dài, rút gọn tiêu đề thay vì vượt độ dài quy định.

## Docstring tiếng Việt

- Dùng dấu `"""` và viết nội dung giải thích bằng tiếng Việt; tên biến, kiểu dữ liệu và tên API giữ nguyên theo code.
- Hàm và method: mô tả mục đích, hành vi, từng tham số, giá trị trả về, các ngoại lệ dự kiến và tác động phụ nếu có (ghi DB/file, kết nối mạng, thay đổi trạng thái hoặc quản lý tài nguyên).
- Class: mô tả trách nhiệm, cách sử dụng, thuộc tính quan trọng và các ràng buộc hoặc vòng đời tài nguyên nếu có. `__init__` có docstring riêng để mô tả tham số khởi tạo và việc khởi tạo trạng thái.
- Dùng nhất quán các mục `Tham số:`, `Trả về:`, `Ngoại lệ:`, `Tác động phụ:` và `Thuộc tính:` khi áp dụng. Không tạo mục trống hoặc bịa hành vi chỉ để đủ mục.
- Mô tả đầy đủ theo độ phức tạp thực tế; không chỉ lặp lại tên hàm/class. Có thể dùng docstring ngắn cho hàm đơn giản nếu đã giải thích đủ hợp đồng sử dụng.

Ví dụ:

```python
# --------------------------- Chuẩn hoá tên source ----------------------------
def normalize_source_name(name: str) -> str:
    """Loại bỏ khoảng trắng ở hai đầu tên source và từ chối tên rỗng.

    Tham số:
        name: Tên source do người dùng nhập.

    Trả về:
        Tên source đã loại bỏ khoảng trắng ở hai đầu.

    Ngoại lệ:
        ValueError: Khi tên chỉ chứa khoảng trắng hoặc là chuỗi rỗng.
    """
    normalized = name.strip()
    if not normalized:
        raise ValueError("Tên source không được để trống.")
    return normalized


# ------------------------ Lớp truy cập dữ liệu source ------------------------
class SourceRepository:
    """Cung cấp thao tác đọc và ghi bản ghi source trong database.

    Lớp này chịu trách nhiệm truy cập dữ liệu, không xử lý upload file
    hoặc chạy inference. API và service sử dụng lớp này để quản lý source.
    """

    ...
```
