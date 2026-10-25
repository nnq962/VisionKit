"""Đọc checkpoint Ultralytics trên CPU bằng restricted loader của PyTorch."""

from pathlib import Path

from app.contracts.model import ModelMetadata
from app.inspection.normalize import class_names, image_size


# ------------------------------ Đọc metadata PT ------------------------------
def inspect_pt(path: Path) -> ModelMetadata:
    """Đọc weights ở path và trích cấu hình/tên class; không forward hoặc tải model khác.

    Chỉ dùng restricted load với các lớp Ultralytics đã cho phép. Từ chối khi
    runtime không hỗ trợ cơ chế này; không fallback sang unpickle không hạn chế.
    Lỗi đọc checkpoint được worker chuyển thành trạng thái failed.
    """
    from ultralytics.nn.tasks import _SafeLoad, torch_safe_load

    if not _SafeLoad.SUPPORTED:
        raise RuntimeError("Runtime thiếu restricted checkpoint loading.")
    checkpoint, _ = torch_safe_load(str(path), safe_only=True)
    model = checkpoint.get("ema")
    if model is None:
        model = checkpoint.get("model")
    model_type = type(model).__name__ if model is not None else None
    known_yolo = {
        "DetectionModel",
        "SegmentationModel",
        "PoseModel",
        "ClassificationModel",
        "OBBModel",
    }
    family = (
        "yoloe"
        if model_type and model_type.startswith("YOLOE")
        else "yolo"
        if model_type in known_yolo
        else None
    )
    config = getattr(model, "yaml", {})
    if not isinstance(config, dict):
        config = {}
    arguments = checkpoint.get("train_args", {})
    if not isinstance(arguments, dict):
        arguments = {}
    model_arguments = getattr(model, "args", {})
    if isinstance(model_arguments, dict):
        arguments = {**arguments, **model_arguments}
    task = arguments.get("task")
    if task not in {"detect", "segment", "pose", "classify", "obb"}:
        mapping = {
            "DetectionModel": "detect",
            "SegmentationModel": "segment",
            "PoseModel": "pose",
            "ClassificationModel": "classify",
            "OBBModel": "obb",
            "YOLOEModel": "detect",
            "YOLOESegModel": "segment",
        }
        task = mapping.get(model_type)
    names = class_names(getattr(model, "names", None))
    count = len(names) or None
    stride = getattr(model, "stride", None)
    if stride is not None and hasattr(stride, "max"):
        stride = int(stride.max().item())
    if not isinstance(stride, int) or not 0 < stride <= 4096:
        stride = None
    parameters = (
        sum(parameter.numel() for parameter in model.parameters()) if family else None
    )
    scale = config.get("scale")
    return ModelMetadata(
        format="pt",
        family=family,
        task=task,
        names=names,
        class_count=count,
        imgsz=image_size(arguments.get("imgsz")),
        stride=stride,
        model_type=model_type,
        scale=scale if scale in {"n", "s", "m", "l", "x"} else None,
        parameters=parameters,
        producer="Ultralytics" if family else None,
        version=str(checkpoint["version"])[:100] if checkpoint.get("version") else None,
    )
