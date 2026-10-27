import { CameraIcon, MonitorIcon } from "lucide-react";
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import type { SourceSelection } from "../use-source-selection";

export function BrowserSourceInput({
  kind,
  selection,
}: {
  kind: "webcam" | "screen";
  selection: SourceSelection;
}) {
  const [deviceIndex, setDeviceIndex] = useState(String(selection.source?.deviceIndex ?? 0));
  const busy = selection.source?.status === "loading";
  return (
    <div className="space-y-4">
      {kind === "webcam" && (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">Webcam trên máy chạy AI. Chỉ dùng khi trình duyệt và server chạy trên cùng máy.</p>
          <Label htmlFor="webcam-index">ID webcam trên máy AI</Label>
          <Input id="webcam-index" type="number" min="0" max="15" step="1" value={deviceIndex} disabled={busy} onChange={(event) => { setDeviceIndex(event.target.value); selection.select(null); }} />
          <p className="text-xs text-muted-foreground">Mặc định 0. Kiểm tra lấy ảnh sau khi camera ổn định rồi nhả camera. Chạy AI để xem hình liên tục.</p>
        </div>
      )}
      {kind === "screen" && (
        <p className="text-sm text-muted-foreground">
          Chụp một ảnh, tự dừng chia sẻ.
        </p>
      )}
        <Button
          variant="outline"
          disabled={busy || (kind === "webcam" && (!deviceIndex.trim() || !Number.isInteger(Number(deviceIndex)) || Number(deviceIndex) < 0 || Number(deviceIndex) > 15))}
          onClick={() =>
            kind === "webcam"
              ? void selection.openCamera(Number(deviceIndex))
              : void selection.captureScreen()
          }
        >
          {kind === "webcam" ? <CameraIcon /> : <MonitorIcon />}
          {busy
            ? "Đang mở…"
            : kind === "webcam"
              ? "Kiểm tra webcam"
              : "Chọn và chụp màn hình"}
        </Button>
      {kind === "webcam" && selection.source?.error && <p role="alert" className="text-sm text-destructive">{selection.source.error}</p>}
      {kind === "webcam" && selection.source?.status === "ready" && <p role="status" className="text-sm text-muted-foreground">Webcam máy AI sẵn sàng.</p>}
      {kind === "screen" && selection.source?.previewUrl && (
        <p className="text-xs text-muted-foreground">Đã chụp ảnh.</p>
      )}
    </div>
  );
}
