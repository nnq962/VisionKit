/* Local uploads and API content URLs both use the native media preview. */
/* eslint-disable @next/next/no-img-element */
import { VideoSourcePreview } from "./video-source-preview";
import { useEffect, useRef } from "react";
import { CameraIcon, FileImageIcon, FilmIcon, RadioIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatBytes, formatDuration } from "../media-metadata";
import { sourceLabel, type VisionSource } from "../types";

function WebcamPreview({ stream }: { stream: MediaStream }) {
  const video = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const element = video.current;
    if (!element) return;
    element.srcObject = stream;
    return () => {
      element.srcObject = null;
    };
  }, [stream]);
  return (
    <video
      ref={video}
      autoPlay
      muted
      playsInline
      className="size-full object-contain"
      aria-label="Preview webcam"
    />
  );
}

export function SourceDetails({
  source,
  onOpenCamera,
}: {
  source: VisionSource | null;
  onOpenCamera?: () => void;
}) {
  const Icon =
    source?.kind === "image" || source?.kind === "screen"
      ? FileImageIcon
      : source?.kind === "video" || source?.kind === "youtube"
        ? FilmIcon
        : CameraIcon;
  return (
    <aside
      className="min-w-0 space-y-6 border-t pt-6 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-6"
      aria-label="Thông tin source"
    >
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold">Thông tin source</h3>
        {source && (
          <span className="rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground">
            {sourceLabel(source.kind)}
          </span>
        )}
      </div>
      <div className="flex aspect-video items-center justify-center overflow-hidden rounded-lg bg-muted">
        {source?.mediaStream ? (
          <WebcamPreview stream={source.mediaStream} />
        ) : source?.previewUrl &&
          (source.kind === "image" || source.kind === "screen") ? (
          <img
            src={source.previewUrl}
            alt={`Xem trước ${source.name}`}
            className="size-full object-contain"
          />
        ) : source?.previewUrl && source.kind === "video" ? (
          <VideoSourcePreview
            key={source.previewUrl}
            url={source.previewUrl}
            name={source.name}
            poster={source.thumbnailUrl}
          />
        ) : (
          <div className="flex flex-col items-center gap-3 px-4 text-center text-muted-foreground">
            <Icon className="size-8" strokeWidth={1.5} />
            <p className="text-xs leading-5">
              {!source
                ? "Chưa chọn source"
                : source.status === "loading"
                  ? "Đang đọc thông tin tệp…"
                  : source.status === "error"
                    ? "Không có preview"
                    : "Chưa có preview"}
            </p>
          </div>
        )}
      </div>
      {source && (
        <>
          <div className="space-y-2">
            <p className="break-all text-sm font-medium">{source.name}</p>
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <RadioIcon className="size-3.5 shrink-0" />
              {source.saved
                ? "Đã lưu"
                : source.status === "ready"
                  ? "Chưa lưu"
                  : source.status === "loading"
                    ? "Đang đọc metadata"
                    : source.status === "error"
                      ? "Không đọc được source"
                      : "Chưa xác minh kết nối"}
            </p>
          </div>
          {source.error && (
            <p role="alert" className="text-sm leading-6 text-destructive">
              {source.error}
            </p>
          )}
          <dl className="divide-y text-sm">
            {[
              [
                "Độ phân giải",
                source.width && source.height
                  ? `${source.width} × ${source.height}`
                  : "Chưa xác định",
              ],
              ["Định dạng", source.format ?? "Chưa xác định"],
              ...(source.kind === "image" ||
              source.kind === "screen" ||
              source.kind === "video"
                ? [["Dung lượng", formatBytes(source.size)]]
                : []),
              ...(source.kind !== "image" && source.kind !== "screen"
                ? [
                    [
                      "Thời lượng",
                      source.kind === "stream" || source.kind === "webcam"
                        ? "Live · không cố định"
                        : formatDuration(source.duration),
                    ],
                    ...(source.kind === "video" && !source.fps
                      ? []
                      : [
                          [
                            "Frame rate",
                            source.fps ? `${source.fps} FPS` : "Chưa xác định",
                          ],
                        ]),
                  ]
                : []),
            ].map(([label, value]) => (
              <div
                key={label}
                className="flex justify-between gap-4 py-3 first:pt-0"
              >
                <dt className="text-muted-foreground">{label}</dt>
                <dd className="text-right font-medium tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
          {source.kind === "webcam" &&
            source.status === "pending" &&
            onOpenCamera && (
              <Button variant="outline" onClick={onOpenCamera}>
                Mở webcam
              </Button>
            )}
        </>
      )}
    </aside>
  );
}
