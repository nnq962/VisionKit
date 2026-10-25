import { useRef, useState } from "react";
import { FileBoxIcon, UploadIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatBytes } from "@/features/sources/media-metadata";
import type { ModelSelection } from "../use-model-selection";

export function ModelUploadForm({ selection }: { selection: ModelSelection }) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [localError, setLocalError] = useState("");
  const [discarding, setDiscarding] = useState(false);
  function choose(files: FileList | null) {
    if (selection.uploading || !files?.length) return;
    setLocalError("");
    setDiscarding(false);
    if (files.length > 1) {
      setLocalError("Chọn một model mỗi lần.");
      return;
    }
    selection.chooseFile(files[0]);
  }
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Label htmlFor="pipeline-model-file">Tệp model</Label>
        <div
          onDragOver={(event) => {
            event.preventDefault();
            if (!selection.uploading) setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            choose(event.dataTransfer.files);
          }}
          className={`rounded-lg border p-4 ${dragging ? "border-primary bg-accent" : "border-input bg-muted/20"} ${selection.file ? "" : "border-dashed"}`}
        >
          {selection.file ? (
            <div className="flex items-start gap-3">
              <FileBoxIcon
                className="mt-1 size-5 shrink-0 text-muted-foreground"
                strokeWidth={1.5}
              />
              <div className="min-w-0 flex-1 space-y-2">
                <p className="break-all text-sm font-medium">
                  {selection.file.name}
                </p>
                <p className="text-xs text-muted-foreground">
                  {formatBytes(selection.file.size)}
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={selection.uploading}
                    onClick={() => input.current?.click()}
                  >
                    Đổi tệp
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={selection.uploading}
                    onClick={() => setDiscarding(true)}
                  >
                    Bỏ tệp
                  </Button>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex min-h-36 flex-col items-center justify-center gap-3 text-center">
              <UploadIcon
                className="size-6 text-muted-foreground"
                strokeWidth={1.5}
              />
              <p className="text-sm font-medium">Kéo thả model vào đây</p>
              <p className="text-xs text-muted-foreground">
                PT, ONNX · Tối đa {formatBytes(selection.maxBytes)}
              </p>
              <Button variant="outline" onClick={() => input.current?.click()}>
                Chọn model
              </Button>
            </div>
          )}
          <input
            ref={input}
            id="pipeline-model-file"
            type="file"
            accept=".pt,.onnx"
            className="sr-only"
            disabled={selection.uploading}
            onChange={(event) => {
              choose(event.target.files);
              event.target.value = "";
            }}
          />
        </div>
        {discarding && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground">
              Bỏ bản nháp này?
            </span>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => {
                selection.discard();
                setDiscarding(false);
              }}
            >
              Bỏ tệp
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setDiscarding(false)}
            >
              Giữ lại
            </Button>
          </div>
        )}
        {localError && (
          <p role="alert" className="text-sm text-destructive">
            {localError}
          </p>
        )}
      </div>
      {selection.file && (
        <>
          <div className="space-y-2">
            <Label htmlFor="pipeline-model-name">Tên model</Label>
            <Input
              id="pipeline-model-name"
              value={selection.name}
              maxLength={120}
              disabled={selection.uploading}
              onChange={(event) =>
                selection.update({ name: event.target.value })
              }
            />
          </div>
          {selection.uploading && (
            <div className="space-y-2">
              <div className="flex justify-between text-xs text-muted-foreground">
                <span role="status">
                  {selection.progress === 100
                    ? "Đang lưu model…"
                    : "Đang tải lên…"}
                </span>
                <span className="tabular-nums">{selection.progress}%</span>
              </div>
              <div
                role="progressbar"
                aria-label="Tiến độ tải model lên"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={selection.progress}
                className="h-1 overflow-hidden rounded bg-muted"
              >
                <div
                  className="h-full bg-primary transition-[width] motion-reduce:transition-none"
                  style={{ width: `${selection.progress}%` }}
                />
              </div>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Button
              disabled={selection.uploading || !selection.name.trim()}
              onClick={() => void selection.save()}
            >
              <UploadIcon />
              {selection.uploading ? "Đang lưu…" : "Lưu và đọc metadata"}
            </Button>
            {selection.uploading && selection.progress < 100 && (
              <Button variant="outline" onClick={selection.cancel}>
                Huỷ tải lên
              </Button>
            )}
          </div>
          <p className="text-xs leading-5 text-muted-foreground">
            Họ model và tác vụ sẽ được nhận diện tự động.
          </p>
        </>
      )}
    </div>
  );
}
