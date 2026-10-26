"use client";

import { useEffect, useRef } from "react";
import { LoaderCircleIcon, RadioIcon, RefreshCwIcon, SquareIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useVideoStream } from "./use-video-stream";

const labels = {
  idle: "Chưa kết nối", connecting: "Đang kết nối", playing: "Đang phát trực tiếp",
  reconnecting: "Đang kết nối lại", stopped: "Đã dừng preview", error: "Không kết nối được",
};

function LiveVideo({ stream, name }: { stream: MediaStream; name: string }) {
  const video = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const element = video.current;
    if (!element) return;
    element.srcObject = stream;
    void element.play().catch(() => {});
    return () => { element.srcObject = null; };
  }, [stream]);
  return <video ref={video} autoPlay muted playsInline aria-label={`Xem trực tiếp ${name}`} className="absolute inset-0 size-full object-contain" />;
}

export function VideoStreamPreview({ sourceId, name }: { sourceId: string; name: string }) {
  const stream = useVideoStream(sourceId);
  const waiting = ["connecting", "reconnecting"].includes(stream.status);
  const active = waiting || stream.status === "playing";
  return (
    <div className="min-w-0 space-y-4" aria-label={`Preview ${name}`}>
      <div className="relative flex aspect-video items-center justify-center overflow-hidden rounded-lg bg-muted">
        {stream.mediaStream ? (
          <LiveVideo stream={stream.mediaStream} name={name} />
        ) : (
          <div className="flex flex-col items-center gap-3 px-6 text-center text-muted-foreground">
            {waiting ? <LoaderCircleIcon className="size-7 animate-spin motion-reduce:animate-none" strokeWidth={1.5} /> : <RadioIcon className="size-7" strokeWidth={1.5} />}
            <p className="text-sm">{labels[stream.status]}</p>
            <p className="text-xs leading-5">
              {stream.status === "stopped" ? "Kết nối lại để tiếp tục xem camera." : waiting ? "Đang chờ hình ảnh từ camera." : "Kiểm tra địa chỉ, tài khoản và mạng của camera."}
            </p>
          </div>
        )}
        {stream.mediaStream && stream.status !== "playing" && (
          <span className="absolute inset-x-0 bottom-0 bg-background/95 px-3 py-2 text-xs">{labels[stream.status].toLowerCase()}</span>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p role="status" className="flex items-center gap-2 text-xs font-medium">
          <span className={`size-2 shrink-0 rounded-full ${stream.status === "playing" ? "bg-success" : waiting ? "bg-amber-500" : "bg-muted-foreground"}`} />
          {labels[stream.status]}{waiting && stream.attempt > 0 ? ` · Lần ${stream.attempt}` : ""}
        </p>
        <div className="flex items-center gap-2">
          {active && <Button size="sm" variant="outline" onClick={stream.stop}><SquareIcon /> Dừng preview</Button>}
          <Button size="sm" variant={active ? "ghost" : "outline"} onClick={stream.reconnect} aria-label={`Kết nối lại ${name}`}>
            <RefreshCwIcon /> Kết nối lại
          </Button>
        </div>
      </div>
      {stream.error && <p role="alert" className={`text-xs leading-5 ${stream.status === "error" ? "text-destructive" : "text-muted-foreground"}`}>{stream.error}</p>}
      <p className="text-xs text-muted-foreground">
        {stream.auth === "accepted" ? "MediaMTX đã đọc được luồng camera" : stream.auth === "rejected" ? "Camera từ chối xác thực" : waiting ? "Đang xác minh kết nối camera" : "Chưa xác minh kết nối camera"}
        {stream.codecs.length ? ` · ${stream.codecs.join(" / ")}` : ""}
      </p>
      <p className="text-xs leading-5 text-muted-foreground">
        {stream.status === "playing" ? "Kết nối được giữ khi bạn chuyển trang." : waiting ? "Tự kết nối lại khi camera có tín hiệu." : stream.status === "stopped" ? "Bấm kết nối lại để tiếp tục xem camera." : "Kiểm tra cấu hình camera rồi thử kết nối lại."}
      </p>
    </div>
  );
}
