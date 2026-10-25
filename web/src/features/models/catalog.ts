export type ModelSize = "n" | "s" | "m" | "l" | "x";
export type ModelTask = "detect" | "segment" | "classify" | "pose" | "obb";
export type ModelFamily = {
  id: string;
  name: string;
  prefix: string;
  description: string;
  sizes: ModelSize[];
  tasks: ModelTask[];
  docs: string;
  openVocabulary?: boolean;
};
export type ModelVariant = {
  id: string;
  familyId: string;
  familyName: string;
  filename: string;
  task: ModelTask | null;
  size: ModelSize | null;
  name?: string | null;
  provider?: string;
  format?: "pt" | "onnx";
  origin?: "catalog" | "upload";
};

export const taskLabels: Record<ModelTask, string> = {
  detect: "Detection",
  segment: "Segmentation",
  classify: "Classification",
  pose: "Pose",
  obb: "OBB",
};
export const sizeLabels: Record<ModelSize, string> = {
  n: "Nano",
  s: "Small",
  m: "Medium",
  l: "Large",
  x: "XLarge",
};
export function modelVariant(
  family: ModelFamily,
  task: ModelTask,
  size: ModelSize,
): ModelVariant {
  const suffix: Record<ModelTask, string> = {
    detect: "",
    segment: "-seg",
    classify: "-cls",
    pose: "-pose",
    obb: "-obb",
  };
  const filename = `${family.prefix}${size}${suffix[task]}.pt`;
  return {
    id: filename,
    filename,
    familyId: family.id,
    familyName: family.name,
    task,
    size,
  };
}

export function modelTaskLabel(task: ModelTask | null) {
  return task ? taskLabels[task] : "Chưa xác định";
}
