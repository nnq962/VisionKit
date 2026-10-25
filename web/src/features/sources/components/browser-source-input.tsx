import { CameraIcon, MonitorIcon, SquareIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { SourceSelection } from "../use-source-selection";

export function BrowserSourceInput({
  kind,
  selection,
}: {
  kind: "webcam" | "screen";
  selection: SourceSelection;
}) {
  const busy = selection.source?.status === "loading";
  const active = kind === "webcam" && Boolean(selection.source?.mediaStream);
  return (
    <div className="space-y-4">
      {kind === "screen" && (
        <p className="text-sm text-muted-foreground">
          Chụp một ảnh, tự dừng chia sẻ.
        </p>
      )}
      {active ? (
        <Button variant="outline" onClick={() => selection.select(null)}>
          <SquareIcon />
          Tắt webcam
        </Button>
      ) : (
        <Button
          variant="outline"
          disabled={busy}
          onClick={() =>
            kind === "webcam"
              ? void selection.openCamera()
              : void selection.captureScreen()
          }
        >
          {kind === "webcam" ? <CameraIcon /> : <MonitorIcon />}
          {busy
            ? "Đang mở…"
            : kind === "webcam"
              ? "Mở webcam"
              : "Chọn và chụp màn hình"}
        </Button>
      )}
      {kind === "screen" && selection.source?.previewUrl && (
        <p className="text-xs text-muted-foreground">Đã chụp ảnh.</p>
      )}
    </div>
  );
}
