import type { StoredModel } from "@/features/models/api";
import type { VisionSource } from "@/features/sources/types";
import type { YoloParameters } from "./types";

export function validateStep(
  step: number,
  source: VisionSource | null,
  model: StoredModel | null,
  parameters: YoloParameters,
) {
  if (step === 0 && !source)
    return "Chọn source mới hoặc một source đã lưu để tiếp tục.";
  if (step === 0 && source?.status === "loading")
    return "Đợi đọc thông tin source trước khi tiếp tục.";
  if (step === 0 && source?.status === "error")
    return "Source chưa hợp lệ. Chọn lại tệp được hỗ trợ.";
  if (step === 1 && !model)
    return "Chọn model đã có hoặc tải lên và lưu model để tiếp tục.";
  if (
    step === 2 &&
    [parameters.confidence, parameters.iou].some(
      (value) =>
        !value.trim() ||
        !Number.isFinite(Number(value)) ||
        Number(value) < 0 ||
        Number(value) > 1,
    )
  )
    return "Confidence và IoU phải là số từ 0 đến 1.";
  return "";
}
