import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { YoloParameters } from "../types";

export function ParametersStep({
  parameters,
  onChange,
}: {
  parameters: YoloParameters;
  onChange: (value: YoloParameters) => void;
}) {
  const { confidence, iou, imageSize, device } = parameters;
  const setConfidence = (confidence: string) =>
    onChange({ ...parameters, confidence });
  const setIou = (iou: string) => onChange({ ...parameters, iou });
  const setImageSize = (imageSize: string) =>
    onChange({ ...parameters, imageSize });
  const setDevice = (device: string) => onChange({ ...parameters, device });
  return (
    <div className="max-w-xl space-y-6">
      <div className="grid gap-6 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="confidence">Confidence threshold</Label>
          <Input
            id="confidence"
            type="number"
            min="0"
            max="1"
            step="0.05"
            value={confidence}
            onChange={(event) => setConfidence(event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="iou">IoU threshold</Label>
          <Input
            id="iou"
            type="number"
            min="0"
            max="1"
            step="0.05"
            value={iou}
            onChange={(event) => setIou(event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="image-size">Image size</Label>
          <Select value={imageSize} onValueChange={setImageSize}>
            <SelectTrigger id="image-size" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {["320", "640", "1280"].map((size) => (
                  <SelectItem key={size} value={size}>
                    {size} px
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="device">Thiết bị</Label>
          <Select value={device} onValueChange={setDevice}>
            <SelectTrigger id="device" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="cpu">CPU</SelectItem>
                <SelectItem value="cuda:0">GPU · CUDA:0</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        Thông số mặc định minh hoạ; thiết bị thực tế phụ thuộc backend.
      </p>
    </div>
  );
}
