import { captureSize, paintCapture, type CaptureSurface } from "./capture-surface.ts";

export type RecordingState = "idle" | "recording" | "stopping";
type RecorderCallbacks = {
  state: (state: RecordingState) => void;
  saved: (blob: Blob) => void;
  error: (message: string) => void;
  notice: (message: string) => void;
};
const MIME_TYPES = ["video/mp4;codecs=avc1", "video/mp4", "video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"];
// Bound browser memory. Save this segment automatically when the limit is reached.
const MAX_BYTES = 256 * 1024 * 1024;

export function recordingMimeType(): string | null {
  if (typeof MediaRecorder === "undefined" || typeof HTMLCanvasElement.prototype.captureStream !== "function") return null;
  return MIME_TYPES.find((type) => MediaRecorder.isTypeSupported(type)) ?? null;
}

export function saveCapture(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export function captureFilename(name: string, extension: string) {
  const base = name.replace(/\.[^.]+$/, "").replace(/[^\p{L}\p{N}_-]+/gu, "-").slice(0, 80) || "ket-qua";
  return `visionkit-${base}-${new Date().toISOString().replace(/[:.]/g, "-")}.${extension}`;
}

/** Owns only its canvas track; it never stops the shared camera or source video. */
export class PreviewRecorder {
  private recorder: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private raf = 0;
  private chunks: Blob[] = [];
  private bytes = 0;
  private stopNotice = "";
  private removeListeners = () => {};
  private completion: Promise<void> | null = null;
  private state: RecordingState = "idle";

  private callbacks: RecorderCallbacks;

  constructor(callbacks: RecorderCallbacks) { this.callbacks = callbacks; }

  start(getSurface: () => CaptureSurface | null) {
    if (this.state !== "idle") return;
    const mimeType = recordingMimeType();
    if (!mimeType) throw new Error("Trình duyệt chưa hỗ trợ ghi video. Hãy thử Chrome hoặc Edge mới nhất.");
    const surface = getSurface();
    if (!surface) throw new Error("Chưa có hình ảnh để ghi.");
    const canvas = document.createElement("canvas");
    Object.assign(canvas, captureSize(surface));
    paintCapture(canvas, surface);
    let recorder: MediaRecorder;
    try {
      this.stream = canvas.captureStream(30);
      recorder = new MediaRecorder(this.stream, { mimeType, videoBitsPerSecond: 6_000_000 });
      this.recorder = recorder;
      this.chunks = [];
      this.bytes = 0;
      this.stopNotice = "";
      this.completion = new Promise<void>((resolve) => {
        recorder.onstop = () => {
          const blob = new Blob(this.chunks, { type: recorder.mimeType || mimeType });
          this.release();
          this.setState("idle");
          try {
            if (blob.size) {
              this.callbacks.saved(blob);
              if (this.stopNotice) this.callbacks.notice(this.stopNotice);
            }
            else this.callbacks.error("Bản ghi trống. Hãy phát video rồi thử lại.");
          } finally { resolve(); }
        };
      });
      recorder.ondataavailable = ({ data }) => {
        if (!data.size) return;
        this.chunks.push(data);
        this.bytes += data.size;
        if (this.bytes >= MAX_BYTES && this.state === "recording") {
          this.stopNotice = "Đã đạt giới hạn 256 MB và lưu bản ghi. Bạn có thể bắt đầu đoạn mới.";
          void this.stop();
        }
      };
      recorder.onerror = () => {
        this.callbacks.error("Ghi video bị gián đoạn. Đang lưu phần đã ghi.");
        void this.stop();
      };
      const ended = () => { void this.stop(); };
      surface.media.addEventListener("ended", ended);
      surface.media.addEventListener("emptied", ended);
      surface.media.addEventListener("error", ended);
      this.removeListeners = () => {
        surface.media.removeEventListener("ended", ended);
        surface.media.removeEventListener("emptied", ended);
        surface.media.removeEventListener("error", ended);
      };
      recorder.start(1000);
      this.setState("recording");
      const paint = () => {
        if (this.state !== "recording") return;
        const current = getSurface();
        if (!current || current.media !== surface.media || !surface.media.isConnected) {
          void this.stop();
          return;
        }
        try { paintCapture(canvas, current); }
        catch {
          this.callbacks.error("Khung hình bị gián đoạn. Đang lưu phần đã ghi.");
          void this.stop();
          return;
        }
        this.raf = requestAnimationFrame(paint);
      };
      this.raf = requestAnimationFrame(paint);
    } catch (error) {
      this.release();
      this.setState("idle");
      throw error;
    }
  }

  stop(): Promise<void> {
    if (this.state === "idle") return Promise.resolve();
    if (this.state === "recording") {
      this.setState("stopping");
      cancelAnimationFrame(this.raf);
      this.removeListeners();
      if (this.recorder?.state !== "inactive") this.recorder?.stop();
    }
    return this.completion ?? Promise.resolve();
  }

  private setState(state: RecordingState) {
    this.state = state;
    this.callbacks.state(state);
  }

  private release() {
    cancelAnimationFrame(this.raf);
    this.removeListeners();
    this.removeListeners = () => {};
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    this.recorder = null;
    this.chunks = [];
    this.bytes = 0;
  }
}
