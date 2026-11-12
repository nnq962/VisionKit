import { useRef, useState } from "react";
import {
  FileImageIcon,
  FilmIcon,
  LoaderCircleIcon,
  UploadIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { formatBytes } from "../media-metadata";
import type { SourceSelection } from "../use-source-selection";

export function FileSourceInput({
  selection,
  kind,
}: {
  selection: SourceSelection;
  kind: "image" | "video";
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const source = selection.source;
  const image = kind === "image";
  const Icon = image ? FileImageIcon : FilmIcon;
  const file = source?.file;
  const hasSelection = Boolean(file || source?.saved);
  const loading = source?.status === "loading";

  function choose(files: FileList | null) {
    setError("");
    if (selection.saving || !files?.length) return;
    if (files.length > 1) {
      setError("Chọn một tệp mỗi lần.");
      return;
    }
    void selection.selectFile(files[0], kind);
  }

  return (
    <div className="space-y-2">
      <Label htmlFor="source-file">{image ? "Tệp ảnh" : "Tệp video"}</Label>
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
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
        className={`rounded-lg border p-4 transition-colors ${dragging ? "border-ring bg-accent" : "border-input bg-muted/20"} ${hasSelection ? "" : "border-dashed"}`}
      >
        {hasSelection && source ? (
          <div className="flex items-start gap-3">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-muted">
              {loading ? (
                <LoaderCircleIcon className="size-5 animate-spin motion-reduce:animate-none" />
              ) : (
                <Icon className="size-5 text-muted-foreground" />
              )}
            </div>
            <div className="min-w-0 flex-1 space-y-1">
              <p className="break-all text-sm font-medium">
                {file?.name ?? source.originalFilename ?? source.name}
              </p>
              <p role="status" className="text-xs text-muted-foreground">
                {formatBytes(file?.size ?? source.size)} ·{" "}
                {loading
                  ? "Đang chuẩn bị…"
                  : source.status === "error"
                    ? "Không đọc được"
                    : source.saved
                      ? "Đã lưu"
                      : "Đã chọn"}
              </p>
              <div className="flex flex-wrap gap-2 pt-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={selection.saving}
                  onClick={() => input.current?.click()}
                >
                  Đổi tệp
                </Button>
                {source.status === "error" && file && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => void selection.selectFile(file, kind)}
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
            <p className="text-sm font-medium">
              Kéo thả {image ? "ảnh" : "video"} vào đây
            </p>
            <p className="text-xs text-muted-foreground">
              {image ? "JPG, PNG, WebP, HEIC/HEIF" : "MP4, MOV, WebM, M4V, OGV"}
            </p>
            <Button
              variant="outline"
              disabled={selection.saving}
              onClick={() => input.current?.click()}
            >
              Chọn tệp
            </Button>
          </div>
        )}
        <input
          ref={input}
          id="source-file"
          type="file"
          className="sr-only"
          disabled={selection.saving}
          accept={
            image
              ? ".jpg,.jpeg,.png,.webp,.gif,.bmp,.avif,.heic,.heif"
              : ".mp4,.webm,.mov,.m4v,.ogv"
          }
          onChange={(event) => {
            choose(event.target.files);
            event.target.value = "";
          }}
        />
      </div>
      {image && !source?.saved && /\.(heic|heif)$/i.test(file?.name ?? "") && (
        <p className="text-xs text-muted-foreground">
          HEIC/HEIF được gửi lên để xem trước.
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
