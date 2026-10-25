export type YoloParameters = {
  confidence: string;
  iou: string;
  imageSize: string;
  device: string;
};

export const defaultParameters: YoloParameters = {
  confidence: "0.25",
  iou: "0.45",
  imageSize: "640",
  device: "cpu",
};
