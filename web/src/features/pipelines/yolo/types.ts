export type YoloParameters = {
  confidence: string;
  iou: string;
  imageSize: string;
  device: string;
  classMode: "all" | "selected";
  classes: string[];
  maxDet: string;
  vidStride: string;
  liveFps: string;
  liveMinutes: string;
  agnosticNms: boolean;
};

export const defaultParameters: YoloParameters = {
  confidence: "0.25",
  iou: "0.7",
  imageSize: "640",
  device: "auto",
  classMode: "all",
  classes: [],
  maxDet: "300",
  vidStride: "1",
  liveFps: "5",
  liveMinutes: "60",
  agnosticNms: false,
};
