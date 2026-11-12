"""Chọn text prompt hoặc class ID theo model cho cấu hình đếm vùng."""

from app.core.errors import SourceError
from app.modules.models.schemas import StoredModel
from app.modules.runs.schemas import RunOptions

from .schemas import CountingConfig


# ------------------------- Chuẩn bị class theo model -------------------------
def counting_options(
    model: StoredModel, config: CountingConfig, options: RunOptions
) -> RunOptions:
    """Kiểm model và trả bản sao options lấy class từ cấu hình đếm.

    Tham số: model đã đọc metadata, cấu hình nhãn/vùng và ngưỡng inference.
    Trả về: YOLOE PT dùng text prompt; YOLO PT/ONNX dùng class ID từ metadata.
    Ngoại lệ: SourceError 422 nếu sai họ/tác vụ hoặc nhãn không thuộc model.
    Không sửa options đầu vào, không tải model và không ghi dữ liệu.
    """
    variant = model.variant
    yoloe = variant.familyId.startswith("yoloe")
    if (
        not variant.familyId.startswith("yolo")
        or variant.task not in {"detect", "segment"}
        or (yoloe and variant.format != "pt")
    ):
        raise SourceError(422, "Đếm vùng hỗ trợ YOLO detect/segment và YOLOE .pt.")
    if yoloe:
        if len(config.classes) > 80:
            raise SourceError(422, "YOLOE hỗ trợ tối đa 80 text prompt.")
        return options.model_copy(
            update={"text_prompts": list(config.classes), "classes": None}
        )
    names = model.inspection.metadata.names if model.inspection.metadata else {}
    if not names or not set(config.classes).issubset(names.values()):
        raise SourceError(422, "Chọn class từ danh sách nhãn có sẵn của model YOLO.")
    try:
        ids = [int(key) for key, name in names.items() if name in config.classes]
    except ValueError as error:
        raise SourceError(422, "Metadata class ID của model không hợp lệ.") from error
    if any(index < 0 for index in ids):
        raise SourceError(422, "Metadata class ID của model không hợp lệ.")
    return options.model_copy(update={"text_prompts": None, "classes": ids})
