import { useRef, useState } from "react";
import { FolderOpenIcon, UploadIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
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
import { RtspSourceInput } from "./rtsp-source-input";
import { VideoSourceInput } from "./video-source-input";
import { BrowserSourceInput } from "./browser-source-input";
import { formatBytes } from "../media-metadata";
import { sourceKinds, type SourceKind } from "../types";
import type { SourceSelection } from "../use-source-selection";

export function NewSourceForm({
  selection,
  allowedKinds,
}: {
  selection: SourceSelection;
  allowedKinds?: SourceKind[];
}) {
  const { kind, location } = selection;
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const isFile = kind === "image" || kind === "video";
  const hint = sourceKinds.find((item) => item.value === kind)!.hint;

  function chooseFile(file?: File) {
    if (file && (kind === "image" || kind === "video")) {
      setError("");
      void selection.selectFile(file, kind);
    }
  }

  function useYoutubeLocation() {
    setError("");
    const value = location.trim();
    try {
      const url = new URL(value);
      const valid =
        ["http:", "https:"].includes(url.protocol) &&
        ["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"].includes(url.hostname) &&
        (url.hostname === "youtu.be"
          ? url.pathname.length > 1
          : Boolean(url.searchParams.get("v")) || /^\/(shorts|live|embed)\/.+/.test(url.pathname));
      if (!valid) throw new Error();
    } catch {
      setError("Nhập URL video YouTube hợp lệ.");
      return;
    }
    void selection.selectYoutube(value);
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Label htmlFor="source-kind">Loại source</Label>
        <Select
          disabled={selection.saving}
          value={kind}
          onValueChange={(value) => {
            selection.setKind(value as SourceKind);
            setError("");
          }}
        >
          <SelectTrigger id="source-kind" className="h-9 w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {sourceKinds
                .filter(
                  (item) => !allowedKinds || allowedKinds.includes(item.value),
                )
                .map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
            </SelectGroup>
          </SelectContent>
        </Select>
        <p className="text-xs leading-5 text-muted-foreground">{hint}</p>
      </div>
      {kind === "stream" ? (
        <RtspSourceInput selection={selection} />
      ) : kind === "video" ? (
        <VideoSourceInput selection={selection} />
      ) : isFile ? (
        <div className="space-y-2">
          <Label htmlFor="source-file">
            {kind === "image" ? "Tệp ảnh" : "Tệp video"}
          </Label>
          <div
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              chooseFile(event.dataTransfer.files[0]);
            }}
            className={`flex min-h-48 flex-col items-center justify-center gap-3 rounded-lg border border-dashed p-6 text-center ${dragging ? "border-primary bg-accent" : "border-input bg-muted/30"}`}
          >
            <UploadIcon
              className="size-6 text-muted-foreground"
              strokeWidth={1.5}
            />
            <p className="text-sm font-medium">
              {selection.source?.file ? (
                <span className="break-all">{selection.source.file.name}</span>
              ) : (
                <>Kéo thả {kind === "image" ? "ảnh" : "video"} vào đây</>
              )}
            </p>
            <p className="text-xs text-muted-foreground">
              {selection.source?.file
                ? `${formatBytes(selection.source.file.size)} · ${selection.source.status === "loading" ? "Đang đọc…" : "Đã chọn"}`
                : "hoặc chọn một tệp từ máy tính"}
            </p>
            <Button
              type="button"
              variant="outline"
              onClick={() => fileInput.current?.click()}
            >
              <FolderOpenIcon />
              {selection.source?.file ? "Đổi tệp" : "Chọn tệp"}
            </Button>
            <input
              ref={fileInput}
              id="source-file"
              type="file"
              className="sr-only"
              accept={
                kind === "image"
                  ? ".jpg,.jpeg,.png,.webp,.gif,.bmp,.avif,.heic,.heif"
                  : ".mp4,.webm,.mov,.m4v,.ogv"
              }
              onChange={(event) => {
                chooseFile(event.target.files?.[0]);
                event.target.value = "";
              }}
            />
          </div>
          {selection.source?.status === "error" && selection.source.file && (
            <Button
              variant="outline"
              onClick={() =>
                void selection.selectFile(
                  selection.source!.file!,
                  kind as "image" | "video",
                )
              }
            >
              Đọc lại tệp
            </Button>
          )}
          {!selection.source?.saved &&
            /\.(heic|heif)$/i.test(selection.source?.file?.name ?? "") && (
              <p className="text-xs text-muted-foreground">
                HEIC/HEIF được gửi lên để xem trước.
              </p>
            )}
        </div>
      ) : kind === "webcam" || kind === "screen" ? (
        <BrowserSourceInput kind={kind} selection={selection} />
      ) : (
        <div className="space-y-2">
          <Label htmlFor="source-location">URL video YouTube</Label>
          <Input
            id="source-location"
            className="h-9"
            value={location}
            onChange={(event) => {
              selection.setLocation(event.target.value);
              setError("");
            }}
            placeholder="https://www.youtube.com/watch?v=…"
            inputMode="url"
          />
          <p className="text-xs leading-5 text-muted-foreground">
            Video thường · tối đa 720p, 200 MiB · bản tạm tự hết hạn.
          </p>
          <Button
            type="button"
            variant="outline"
            className="mt-2"
            onClick={useYoutubeLocation}
          >
            {selection.source?.status === "loading" ? "Chuẩn bị lại video" : "Chuẩn bị video"}
          </Button>
          {selection.source?.kind === "youtube" && (
            <div className="space-y-2 pt-2">
              {selection.source.status === "loading" && <p role="status" className="text-sm text-muted-foreground">Đang chuẩn bị video YouTube…</p>}
              {selection.source.status === "ready" && <p role="status" className="text-sm text-muted-foreground">Video sẵn sàng. Có thể xem, tua và tiếp tục chạy AI.</p>}
              {selection.source.error && <p role="alert" className="text-sm text-destructive">{selection.source.error}</p>}
              <Button variant="destructive" onClick={() => void selection.discardYoutube()}>{selection.source.status === "loading" ? "Huỷ chuẩn bị" : "Xoá video tạm"}</Button>
            </div>
          )}
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
