"""Đọc graph và metadata ONNX, không mở file tensor external hoặc chạy ONNX Runtime."""

from pathlib import Path

from app.contracts.model import ModelMetadata
from app.inspection.identity import model_identity
from app.inspection.normalize import class_names, image_size, literal


# ----------------------------- Đọc metadata ONNX -----------------------------
def inspect_onnx(path: Path) -> ModelMetadata:
    """Parse protobuf tại path, trả metadata và shape thực; không chạy graph hoặc đọc file phụ.

    ONNX không nhúng family/task vẫn trả shape; service đánh dấu needs_input.
    Lỗi protobuf/graph không hợp lệ được worker chuyển thành failed.
    """
    import onnx

    model = onnx.load(str(path), load_external_data=False)
    if not model.ir_version or not model.graph.output:
        raise ValueError("ONNX thiếu graph hoặc phiên bản IR.")
    values = {item.key: item.value for item in model.metadata_props}
    description = values.get("description", "").lower()
    declared_family = values.get("family", "").lower()
    family = (
        declared_family
        if declared_family in {"yolo", "yoloe"}
        else "yoloe"
        if "ultralytics" in description and "yoloe" in description
        else "yolo"
        if "ultralytics" in description and "yolo" in description
        else None
    )
    task = values.get("task")
    if task not in {"detect", "segment", "pose", "classify", "obb"}:
        task = None
    initializers = {item.name for item in model.graph.initializer}
    inputs = [item for item in model.graph.input if item.name not in initializers]
    shape = None
    if inputs:
        shape = [
            dim.dim_value if dim.HasField("dim_value") else dim.dim_param or None
            for dim in inputs[0].type.tensor_type.shape.dim
        ][:8]
    series, declared_scale = model_identity(
        values.get("model_series") or values.get("description"), family
    )
    scale = values.get("scale") or declared_scale
    names = class_names(values.get("names"))
    stride = literal(values.get("stride"))
    return ModelMetadata(
        format="onnx",
        family=family,
        model_series=series,
        series_source="onnx_metadata" if series else None,
        scale=scale if scale in {"n", "s", "m", "l", "x"} else None,
        ultralytics_version=values.get("version", "")[:100] or None if family else None,
        task=task,
        names=names,
        class_count=len(names) or None,
        imgsz=image_size(values.get("imgsz")),
        input_shape=shape,
        stride=stride if isinstance(stride, int) and 0 < stride <= 4096 else None,
        producer=(model.producer_name or values.get("author") or "ONNX")[:100],
        version=values.get("version", model.producer_version or "")[:100] or None,
    )
