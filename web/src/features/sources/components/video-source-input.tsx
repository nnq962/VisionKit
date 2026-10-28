import { useRef, useState } from "react";
import { FilmIcon, LoaderCircleIcon, UploadIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { formatBytes } from "../media-metadata";
import type { VisionSource } from "../types";

export function VideoSourceInput({
  selection,
  disabled = false,
}: {
  disabled?: boolean;
  selection: {
    source: Pick<VisionSource, "file" | "status"> | null;
    selectFile: (file: File, kind: "video") => void | Promise<unknown>;
  };
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const source = selection.source;
  const file = source?.file;
  const loading = source?.status === "loading";

  function choose(files: FileList | null) {
    setError("");
    if (disabled || !files?.length) return;
    if (!/\.(mp4|webm|mov|m4v|ogv)$/i.test(files[0].name)) {
      setError("Chọn video MP4, MOV, WebM, M4V hoặc OGV.");
      return;
    }
    if (files.length > 1) {
      setError("Chọn một video mỗi lần.");
      return;
    }
    void selection.selectFile(files[0], "video");
  }

  return (
    <div className="space-y-2">
      <Label htmlFor="video-file">Tệp video</Label>
      <div
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null))
            setDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          choose(event.dataTransfer.files);
        }}
        className={`rounded-lg border p-4 transition-colors ${dragging ? "border-primary bg-accent" : "border-input bg-muted/20"} ${file ? "" : "border-dashed"}`}
      >
        {file ? (
          <div className="flex items-start gap-3">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-muted">
              {loading ? (
                <LoaderCircleIcon className="size-5 animate-spin motion-reduce:animate-none" />
              ) : (
                <FilmIcon className="size-5 text-muted-foreground" />
              )}
            </div>
            <div className="min-w-0 flex-1 space-y-1">
              <p className="break-all text-sm font-medium">{file.name}</p>
              <p role="status" className="text-xs text-muted-foreground">
                {formatBytes(file.size)} ·{" "}
                {loading
                  ? "Đang đọc…"
                  : source?.status === "error"
                    ? "Không đọc được"
                    : "Đã chọn"}
              </p>
              <div className="flex flex-wrap gap-2 pt-2">
                <Button
                  type="button"
                  disabled={disabled}
                  variant="outline"
                  size="sm"
                  onClick={() => input.current?.click()}
                >
                  Đổi video
                </Button>
                {source?.status === "error" && (
                  <Button
                    type="button"
                    disabled={disabled}
                    variant="ghost"
                    size="sm"
                    onClick={() => void selection.selectFile(file, "video")}
                  >
                    Thử lại
                  </Button>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="flex min-h-44 flex-col items-center justify-center gap-3 text-center">
            <UploadIcon
              className="size-6 text-muted-foreground"
              strokeWidth={1.5}
            />
            <p className="text-sm font-medium">Kéo thả video vào đây</p>
            <p className="text-xs text-muted-foreground">
              MP4, MOV, WebM, M4V, OGV
            </p>
            <Button type="button" disabled={disabled} variant="outline" onClick={() => input.current?.click()}>
              Chọn video
            </Button>
          </div>
        )}
        <input
          ref={input}
          id="video-file"
          type="file"
          disabled={disabled}
          className="sr-only"
          accept=".mp4,.webm,.mov,.m4v,.ogv"
          onChange={(event) => {
            choose(event.target.files);
            event.target.value = "";
          }}
        />
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
