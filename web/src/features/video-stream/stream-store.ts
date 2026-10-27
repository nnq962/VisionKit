import { openWebRtcStream, StreamFailure, type CameraStatus, type StreamCallbacks, type StreamConnection } from "./webrtc-client.ts";

export type VideoStreamStatus = "idle" | "connecting" | "playing" | "reconnecting" | "stopped" | "error";
export type VideoStreamSnapshot = {
  status: VideoStreamStatus;
  mediaStream: MediaStream | null;
  auth: CameraStatus["auth"];
  codecs: string[];
  attempt: number;
  error: string | null;
};
export const EMPTY_STREAM: VideoStreamSnapshot = Object.freeze({
  status: "idle", mediaStream: null, auth: "unknown", codecs: [], attempt: 0, error: null,
});
export type StreamEnvironment = {
  open: (id: string, callbacks: StreamCallbacks, signal: AbortSignal, temporaryUrl?: string) => Promise<StreamConnection>;
  random: () => number;
  later: (callback: () => void, delay: number) => ReturnType<typeof setTimeout>;
  cancel: (timer: ReturnType<typeof setTimeout>) => void;
};
type Entry = {
  snapshot: VideoStreamSnapshot;
  listeners: Set<() => void>;
  connection: StreamConnection | null;
  controller: AbortController | null;
  timer: ReturnType<typeof setTimeout> | null;
  deadline: ReturnType<typeof setTimeout> | null;
  enabled: boolean;
  generation: number;
  failures: number;
  temporaryUrl?: string;
  connectedOnce?: boolean;
};

export function browserStreamEnvironment(): StreamEnvironment {
  return {
    open: openWebRtcStream, random: () => Math.random(),
    later: (callback, delay) => setTimeout(callback, delay), cancel: (timer) => clearTimeout(timer),
  };
}

/** Persistent WebRTC ownership; route subscribers never own the connection. */
export class VideoStreamStore {
  private entries = new Map<string, Entry>();
  private env: StreamEnvironment;
  private limit: number;
  constructor(env: StreamEnvironment, limit = 4) { this.env = env; this.limit = limit; }

  private entry(id: string): Entry {
    let entry = this.entries.get(id);
    if (!entry) {
      entry = { snapshot: EMPTY_STREAM, listeners: new Set(), connection: null, controller: null,
        timer: null, deadline: null, enabled: false, generation: 0, failures: 0 };
      this.entries.set(id, entry);
    }
    return entry;
  }
  snapshot = (id: string) => this.entries.get(id)?.snapshot ?? EMPTY_STREAM;
  subscribe = (id: string, listener: () => void) => {
    const entry = this.entry(id);
    entry.listeners.add(listener);
    return () => { entry.listeners.delete(listener); };
  };
  private publish(entry: Entry, update: Partial<VideoStreamSnapshot>) {
    entry.snapshot = { ...entry.snapshot, ...update };
    entry.listeners.forEach((listener) => listener());
  }
  start = (id: string) => {
    const entry = this.entry(id);
    if (entry.enabled) return;
    if ([...this.entries.values()].filter((item) => item.enabled).length >= this.limit) {
      this.publish(entry, { status: "error", error: "Đã mở tối đa bốn camera. Dừng một camera trước." });
      return;
    }
    entry.enabled = true;
    entry.failures = 0;
    entry.connectedOnce = false;
    this.connect(id, entry);
  };
  startTemporary = (id: string, url: string) => {
    const entry = this.entry(id);
    if (entry.enabled) this.stop(id);
    entry.temporaryUrl = url;
    this.start(id);
  };
  discardTemporary = (id: string) => {
    const entry = this.entries.get(id);
    if (!entry?.temporaryUrl) return;
    this.stop(id);
    entry.temporaryUrl = undefined;
  };
  private clearTransport(entry: Entry) {
    entry.generation++;
    if (entry.timer !== null) this.env.cancel(entry.timer);
    if (entry.deadline !== null) this.env.cancel(entry.deadline);
    entry.timer = entry.deadline = null;
    entry.controller?.abort();
    entry.controller = null;
    const closing = entry.connection?.close();
    entry.connection = null;
    return closing;
  }
  private fail(id: string, entry: Entry, error: unknown) {
    if (!entry.enabled) return;
    this.clearTransport(entry);
    const failure = error instanceof StreamFailure ? error : new StreamFailure("Không kết nối được dịch vụ WebRTC. Đang thử lại…");
    if (!failure.retryable) {
      entry.enabled = false;
      this.publish(entry, { status: "error", mediaStream: null, error: failure.message,
        auth: failure.code === "auth_failed" ? "rejected" : entry.snapshot.auth });
      return;
    }
    entry.failures++;
    this.publish(entry, { status: "reconnecting", mediaStream: null, attempt: entry.failures, error: failure.message });
    const delay = Math.min(30000, 1000 * 2 ** Math.min(entry.failures - 1, 5)) * (0.8 + this.env.random() * 0.4);
    entry.timer = this.env.later(() => { entry.timer = null; if (entry.enabled) this.connect(id, entry); }, delay);
  }
  private connect(id: string, entry: Entry) {
    this.clearTransport(entry);
    const generation = entry.generation;
    const current = () => entry.enabled && generation === entry.generation;
    const controller = new AbortController();
    entry.controller = controller;
    this.publish(entry, { status: entry.failures ? "reconnecting" : "connecting", mediaStream: null, auth: "unknown", error: null });
    entry.deadline = this.env.later(() => {
      if (current()) this.fail(id, entry, new StreamFailure(
        entry.temporaryUrl && !entry.connectedOnce ? "Chưa đọc được camera. Kiểm tra địa chỉ và mạng rồi thử lại." : "Chưa thiết lập được WebRTC. Đang thử lại…",
        !entry.temporaryUrl || Boolean(entry.connectedOnce),
      ));
    }, 35000);
    const onStatus = (camera: CameraStatus) => {
      if (!current()) return;
      this.publish(entry, { auth: camera.auth, codecs: camera.codecs });
      if (camera.status === "error") {
        this.fail(id, entry, new StreamFailure(camera.message ?? "Camera từ chối kết nối.", camera.retryable ?? false, camera.code));
      } else if (camera.status !== "ready") {
        this.publish(entry, { status: camera.status, error: camera.message ?? null });
      }
    };
    void this.env.open(id, {
      stream: (mediaStream) => { if (current()) this.publish(entry, { mediaStream }); },
      state: (state) => {
        if (!current()) return;
        if (state === "connected") {
          entry.connectedOnce = true;
          if (entry.deadline !== null) this.env.cancel(entry.deadline);
          entry.deadline = null;
          this.publish(entry, { status: "playing", attempt: 0, error: null });
        } else this.publish(entry, { status: "reconnecting", error: "WebRTC đang khôi phục kết nối…" });
      },
      status: onStatus,
      error: (error) => { if (current()) this.fail(id, entry, error); },
    }, controller.signal, entry.temporaryUrl).then((connection) => {
      if (!current()) { connection.close(); return; }
      entry.connection = connection;
      const poll = async () => {
        if (!current()) return;
        try {
          onStatus(await connection.status(controller.signal));
          if (current()) entry.timer = this.env.later(() => { void poll(); }, 2000);
        } catch (error) { if (current()) this.fail(id, entry, error); }
      };
      entry.timer = this.env.later(() => { void poll(); }, 2000);
    }).catch((error) => { if (current()) this.fail(id, entry, error); });
  }
  stop = (id: string) => {
    const entry = this.entries.get(id);
    if (!entry) return;
    entry.enabled = false;
    const closing = this.clearTransport(entry);
    this.publish(entry, { ...EMPTY_STREAM, status: "stopped" });
    return closing;
  };
  reconnect = (id: string) => { this.stop(id); this.start(id); };
  configurationChanged = (id: string) => {
    const entry = this.entries.get(id);
    if (entry && entry.snapshot.status !== "stopped" && entry.snapshot.status !== "idle") this.reconnect(id);
  };
  online = () => {
    this.entries.forEach((entry, id) => {
      if (entry.enabled && entry.snapshot.status === "reconnecting") this.connect(id, entry);
    });
  };
  dispose = () => { this.entries.forEach((_, id) => this.stop(id)); this.entries.clear(); };
}
