import { validateTextPrompts } from "./text-prompts";
import type { StoredModel } from "@/features/models/api";
import type { VisionSource } from "@/features/sources/types";
import { defaultParameters, type YoloParameters } from "./types";

export const deviceLabels: Record<string, string> = {
  auto: "Tự động",
  cpu: "CPU",
  "cuda:0": "GPU · CUDA:0",
  mps: "Apple · MPS",
};
export function imageSizeLabel(size: string) {
  const [height, width = height] = size.split("x");
  return `${height} × ${width}`;
}
export function fixedImageSize(model: StoredModel | null): string | null {
  const shape = model?.inspection.metadata?.input_shape;
  if (model?.format !== "onnx" || shape?.length !== 4) return null;
  const [height, width] = shape.slice(2);
  if (
    typeof height !== "number" ||
    typeof width !== "number" ||
    height <= 0 ||
    width <= 0
  )
    return null;
  return height === width ? String(height) : `${height}x${width}`;
}
export function modelImageSize(model: StoredModel | null) {
  const size = model?.inspection.metadata?.imgsz;
  return (
    fixedImageSize(model) ??
    (size?.length === 2
      ? size[0] === size[1]
        ? String(size[0])
        : size.join("x")
      : "640")
  );
}
export function isTemporalSource(source: VisionSource | null) {
  return Boolean(
    source && ["video", "stream", "webcam", "youtube"].includes(source.kind),
  );
}
export function parametersForModel(model: StoredModel | null): YoloParameters {
  return {
    ...defaultParameters,
    classes: [],
    textPromptEnabled: Boolean(model?.familyId.startsWith("yoloe")),
    imageSize: modelImageSize(model),
  };
}
export function validateParameters(
  parameters: YoloParameters,
  model: StoredModel | null,
  source: VisionSource | null,
): string {
  if (model?.familyId.startsWith("yoloe")) {
    if (model.format !== "pt") return "Text prompt cần model YOLOE .pt, không dùng ONNX.";
    const error = validateTextPrompts(parameters.textPrompts);
    if (error) return error;
  }
  const classify = model?.task === "classify";
  if (
    !classify &&
    [parameters.confidence, parameters.iou].some(
      (value) =>
        !value.trim() ||
        !Number.isFinite(Number(value)) ||
        Number(value) < 0 ||
        Number(value) > 1,
    )
  )
    return "Confidence và IoU phải là số từ 0 đến 1.";
  const fixed = fixedImageSize(model);
  const dimensions = parameters.imageSize.split("x").map(Number);
  const stride = model?.inspection.metadata?.stride ?? 32;
  if (
    fixed
      ? parameters.imageSize !== fixed
      : dimensions.length > 2 ||
        dimensions.some(
          (value) =>
            !Number.isInteger(value) ||
            value < 32 ||
            value > 4096 ||
            value % stride !== 0,
        )
  )
    return fixed
      ? "Kích thước đầu vào phải khớp model ONNX."
      : `Kích thước đầu vào phải chia hết cho stride ${stride}.`;
  if (!deviceLabels[parameters.device]) return "Chọn thiết bị chạy hợp lệ.";
  if (
    !classify &&
    (!parameters.maxDet.trim() ||
      !Number.isInteger(Number(parameters.maxDet)) ||
      Number(parameters.maxDet) < 1 ||
      Number(parameters.maxDet) > 3000)
  )
    return "Số kết quả tối đa phải từ 1 đến 3000.";
  if (
    isTemporalSource(source) &&
    (!parameters.vidStride.trim() ||
      !Number.isInteger(Number(parameters.vidStride)) ||
      Number(parameters.vidStride) < 1 ||
      Number(parameters.vidStride) > 120)
  )
    return "Bước lấy frame phải là số nguyên từ 1 đến 120.";
  if (source && ["stream", "webcam"].includes(source.kind)) {
    if (!parameters.liveFps.trim() || !Number.isFinite(Number(parameters.liveFps)) || Number(parameters.liveFps) < 1 || Number(parameters.liveFps) > 60)
      return "Giới hạn AI phải từ 1 đến 60 FPS.";
    if (!parameters.liveMinutes.trim() || !Number.isInteger(Number(parameters.liveMinutes)) || Number(parameters.liveMinutes) < 1 || Number(parameters.liveMinutes) > 240)
      return "Thời lượng phải là số phút từ 1 đến 240.";
  }
  const names = model?.inspection.metadata?.names ?? {};
  if (
    !classify &&
    !model?.familyId.startsWith("yoloe") &&
    parameters.classMode === "selected" &&
    (!parameters.classes.length ||
      parameters.classes.some((id) => !(id in names)))
  )
    return "Chọn ít nhất một class hợp lệ hoặc dùng tất cả class.";
  return "";
}
