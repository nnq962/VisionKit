"""Nạp model Ultralytics local và chạy một ảnh, không tải model từ mạng."""

import time
from pathlib import Path
from typing import Any

from app.adapters.ultralytics.results import serialize_result
from app.contracts.prediction import ModelPredictRequest, PredictRequest
from app.media_sources import SourceType, create_media_source


# ------------------------------ Nạp model local ------------------------------
def load_model(model_path: Path, request: ModelPredictRequest) -> tuple[Any, str]:
    """Kiểm tra restricted loader, ONNX và thiết bị rồi nạp weights một lần cho mỗi lượt chạy."""
    import torch
    from ultralytics import YOLO, YOLOE
    from ultralytics.nn.tasks import _SafeLoad
    from ultralytics.utils import SAFE_LOAD

    if not _SafeLoad.SUPPORTED or not SAFE_LOAD:
        raise ValueError("Runtime không hỗ trợ restricted loading.")
    options = request.options
    device = options.device
    if device == "auto":
        device = (
            "cpu"
            if model_path.suffix == ".onnx"
            else "cuda:0"
            if torch.cuda.is_available()
            else "mps"
            if torch.backends.mps.is_available()
            else "cpu"
        )
    if device == "cuda:0" and not torch.cuda.is_available():
        raise ValueError("Không có GPU CUDA. Hãy chọn CPU hoặc Tự động.")
    if device == "mps" and not torch.backends.mps.is_available():
        raise ValueError("Không có thiết bị MPS. Hãy chọn CPU hoặc Tự động.")
    if model_path.suffix == ".onnx":
        if device != "cpu":
            raise ValueError("ONNX hiện dùng CPU. Hãy chọn CPU hoặc Tự động.")
        import onnx

        model_proto = onnx.load(model_path, load_external_data=False)
        if any(
            tensor.data_location == onnx.TensorProto.EXTERNAL
            for tensor in onnx.external_data_helper._get_all_tensors(model_proto)
        ):
            raise ValueError("ONNX external weights chưa được hỗ trợ.")
        dims = model_proto.graph.input[0].type.tensor_type.shape.dim
        if len(dims) == 4:
            if dims[0].HasField("dim_value") and dims[0].dim_value != 1:
                raise ValueError("Inference ảnh yêu cầu ONNX batch bằng 1.")
            for dim, size in zip(dims[2:], options.imgsz):
                if dim.HasField("dim_value") and dim.dim_value != size:
                    raise ValueError("Kích thước đầu vào không khớp ONNX.")
    if any(size < 32 or size > 4096 for size in options.imgsz):
        raise ValueError("Kích thước đầu vào không hợp lệ.")
    model = (YOLOE if request.family == "yoloe" else YOLO)(
        str(model_path), task=request.task
    )
    return model, device


# ------------------------------ Chạy ảnh đơn ---------------------------------
def predict_image(model_path: Path, image_path: Path, request: PredictRequest) -> dict:
    """Giải mã ảnh theo EXIF và predict, trả JSON toạ độ gốc; không vẽ hoặc ghi ảnh."""
    options = request.options
    with create_media_source(image_path, source_type=SourceType.IMAGE) as reader:
        image, _ = next(reader)
        started = time.perf_counter()
        model, device = load_model(model_path, request)
        result = model.predict(
            source=image,
            conf=options.conf,
            iou=options.iou,
            imgsz=list(options.imgsz),
            device=device,
            classes=options.classes,
            max_det=options.max_det,
            agnostic_nms=options.agnostic_nms,
            save=False,
            verbose=False,
        )[0]
        return serialize_result(result, device, time.perf_counter() - started)
