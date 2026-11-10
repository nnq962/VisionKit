"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { CameraIcon, CircleIcon, SquareIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { captureSize, paintCapture, surfaceReady, type CaptureSurface } from "./capture-surface";
import { captureFilename, PreviewRecorder, recordingMimeType, saveCapture, type RecordingState } from "./preview-recorder";

function captureError(cause: unknown, fallback: string) {
  if (cause instanceof DOMException && cause.name === "SecurityError")
    return "Nguồn ảnh hoặc video chưa cho phép lưu từ trình duyệt. Hãy kiểm tra quyền truy cập nguồn.";
  return cause instanceof Error ? cause.message : fallback;
}

export function ResultCapture({ children, name, temporal }: { children: ReactNode; name: string; temporal: boolean }) {
  const container = useRef<HTMLDivElement>(null);
  const controller = useRef<PreviewRecorder | null>(null);
  const [state, setState] = useState<RecordingState>("idle");
  const [ready, setReady] = useState(false);
  const [supported, setSupported] = useState(false);
  const [savingImage, setSavingImage] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  function getSurface(): CaptureSurface | null {
    const media = container.current?.querySelector<HTMLVideoElement | HTMLImageElement | HTMLCanvasElement>("[data-capture-media]");
    return media ? { media, overlay: container.current?.querySelector<HTMLCanvasElement>("[data-capture-overlay]") } : null;
  }

  useEffect(() => {
    const check = () => {
      const media = container.current?.querySelector<HTMLVideoElement | HTMLImageElement | HTMLCanvasElement>("[data-capture-media]");
      setReady(Boolean(media && surfaceReady({ media })));
    };
    const initial = requestAnimationFrame(() => {
      setSupported(recordingMimeType() !== null);
      check();
    });
    const timer = setInterval(check, 300);
    return () => { clearInterval(timer); cancelAnimationFrame(initial); };
  }, []);

  useEffect(() => {
    const recorder = new PreviewRecorder({
      state: setState,
      saved: (blob) => {
        saveCapture(blob, captureFilename(name, blob.type.includes("mp4") ? "mp4" : "webm"));
        setNotice("Đã tải xuống bản ghi.");
      },
      error: setError,
      notice: setNotice,
    });
    controller.current = recorder;
    return () => {
      controller.current = null;
      void recorder.stop();
    };
  }, [name]);

  useEffect(() => {
    if (state !== "recording") return;
    const started = Date.now();
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => { clearInterval(timer); };
  }, [state]);

  useEffect(() => {
    if (state === "idle") return;
    const hidden = () => {
      if (document.hidden) {
        void controller.current?.stop().then(() => setNotice("Đã dừng và lưu bản ghi khi tab bị ẩn."));
      }
    };
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    document.addEventListener("visibilitychange", hidden);
    window.addEventListener("beforeunload", warn);
    return () => {
      document.removeEventListener("visibilitychange", hidden);
      window.removeEventListener("beforeunload", warn);
    };
  }, [state]);

  function start() {
    setError("");
    setNotice("");
    setSeconds(0);
    try { controller.current?.start(getSurface); }
    catch (cause) { setError(captureError(cause, "Không thể bắt đầu ghi video.")); }
  }

  async function snapshot() {
    setError("");
    setNotice("");
    setSavingImage(true);
    try {
      const surface = getSurface();
      if (!surface) throw new Error("Chưa có hình ảnh để lưu.");
      const canvas = document.createElement("canvas");
      Object.assign(canvas, captureSize(surface));
      paintCapture(canvas, surface);
      const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
      if (!blob) throw new Error("Không thể tạo ảnh. Hãy thử lại.");
      saveCapture(blob, captureFilename(name, "png"));
      setNotice("Đã tải xuống ảnh kết quả.");
    } catch (cause) {
      setError(captureError(cause, "Không thể lưu ảnh kết quả."));
    } finally { setSavingImage(false); }
  }

  return (
    <div className="space-y-3">
      <div ref={container}>{children}</div>
      <div className="flex flex-wrap items-center gap-2" aria-label="Lưu kết quả">
        {temporal && (state === "idle" ? (
          <Button type="button" size="sm" variant="outline" disabled={!ready || !supported} onClick={start}>
            <CircleIcon className="text-destructive" /> Bắt đầu ghi
          </Button>
        ) : (
          <Button type="button" size="sm" variant="destructive" disabled={state === "stopping"} onClick={() => void controller.current?.stop()}>
            <SquareIcon /> {state === "stopping" ? "Đang lưu video…" : "Dừng và lưu video"}
          </Button>
        ))}
        <Button type="button" size="sm" variant="outline" disabled={!ready || savingImage} onClick={() => void snapshot()}>
          <CameraIcon /> {savingImage ? "Đang lưu ảnh…" : "Chụp ảnh"}
        </Button>
        {state === "recording" && (
          <span role="status" className="flex items-center gap-2 text-xs tabular-nums text-destructive">
            <span className="size-2 rounded-full bg-destructive" />
            Đang ghi · {Math.floor(seconds / 60).toString().padStart(2, "0")}:{(seconds % 60).toString().padStart(2, "0")}
          </span>
        )}
      </div>
      {temporal && <p className="text-xs text-muted-foreground">Ghi kèm kết quả AI, không âm thanh.{state !== "idle" ? " Tự lưu khi ẩn tab hoặc rời trang." : ""}</p>}
      {temporal && !supported && <p className="text-xs text-muted-foreground">Nếu nút ghi không khả dụng, hãy dùng trình duyệt hỗ trợ ghi video như Chrome hoặc Edge.</p>}
      {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
      {notice && <p role="status" className="text-xs text-muted-foreground">{notice}</p>}
    </div>
  );
}
