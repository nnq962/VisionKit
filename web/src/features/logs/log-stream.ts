export type LogLevel = "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";
export type LogEntry = {
  id: string;
  timestamp: string;
  service: "backend" | "ai";
  level: LogLevel;
  logger: string;
  message: string;
  run_id: string | null;
  traceback: string | null;
  source_id: string | null;
};
export type AiLogStatus = {
  configured: boolean;
  available: boolean | null;
  last_success_at: string | null;
  reset_count: number;
  dropped_batches: number;
};
export type LogPage = {
  items: LogEntry[];
  next_cursor: string;
  has_more: boolean;
  reset: boolean;
  dropped: boolean;
  ai: AiLogStatus;
};
export type LogState = {
  entries: LogEntry[];
  ai: AiLogStatus | null;
  connection: "connecting" | "online" | "offline";
  notice: string | null;
};
export const MAX_LOG_ENTRIES = 2000;
export const INITIAL_LOG_STATE: LogState = { entries: [], ai: null, connection: "connecting", notice: null };
const CURSOR = /^[a-f0-9]{32}:[0-9]{1,20}$/;

export function parseLogPage(value: unknown): LogPage {
  const page = value as LogPage | null;
  const ai = page?.ai;
  if (!page || !Array.isArray(page.items) || page.items.length > 500 ||
      typeof page.next_cursor !== "string" || !CURSOR.test(page.next_cursor) ||
      typeof page.has_more !== "boolean" || typeof page.reset !== "boolean" ||
      typeof page.dropped !== "boolean" || !ai || typeof ai.configured !== "boolean" ||
      (ai.available !== null && typeof ai.available !== "boolean") ||
      (ai.last_success_at !== null && typeof ai.last_success_at !== "string") ||
      !Number.isSafeInteger(ai.reset_count) || ai.reset_count < 0 ||
      !Number.isSafeInteger(ai.dropped_batches) || ai.dropped_batches < 0 ||
      !page.items.every((entry) => entry && typeof entry.id === "string" && CURSOR.test(entry.id) &&
        typeof entry.timestamp === "string" && Number.isFinite(Date.parse(entry.timestamp)) &&
        (entry.service === "backend" || entry.service === "ai") &&
        ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"].includes(entry.level) &&
        typeof entry.logger === "string" && typeof entry.message === "string" && entry.message.length <= 8192 &&
        (entry.run_id === null || typeof entry.run_id === "string") &&
        (entry.traceback === null || (typeof entry.traceback === "string" && entry.traceback.length <= 8192)))) {
    throw new Error("Phản hồi log không hợp lệ.");
  }
  return page;
}

export function mergeLogPage(state: LogState, page: LogPage): LogState {
  const retained = page.reset ? [] : state.entries;
  const ids = new Set(retained.map((entry) => entry.id));
  const incoming = page.items.filter((entry) => {
    if (ids.has(entry.id)) return false;
    ids.add(entry.id);
    return true;
  });
  let notice = state.notice;
  if (page.reset) notice = "Backend đã khởi động lại. Lịch sử log đã được đặt lại.";
  else if (page.dropped) notice = "Một số log chưa đọc đã hết hạn trong bộ đệm.";
  else if (state.ai && (page.ai.reset_count > state.ai.reset_count || page.ai.dropped_batches > state.ai.dropped_batches)) {
    notice = "Lịch sử log AI bị gián đoạn. Một số log có thể không còn đầy đủ.";
  }
  return { entries: incoming.length || page.reset ? [...retained, ...incoming].slice(-MAX_LOG_ENTRIES) : retained,
    ai: page.ai, connection: "online", notice };
}

// Một lượt đọc tại một thời điểm; cursor được giữ khi tạm dừng/đóng/mất kết nối.
export class LogStream {
  state: LogState = INITIAL_LOG_STATE;
  private cursor: string | null = null;
  private active = false;
  private generation = 0;
  private failures = 0;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private controller: AbortController | undefined;

  private readonly onChange: (state: LogState) => void;
  private readonly request: typeof fetch;

  constructor(onChange: (state: LogState) => void, request: typeof fetch = (input, init) => fetch(input, init)) {
    this.onChange = onChange;
    this.request = request;
  }

  start() {
    if (this.active) return;
    this.active = true;
    this.failures = 0;
    void this.poll(this.generation);
  }

  stop() {
    this.active = false;
    this.generation++;
    clearTimeout(this.timer);
    this.controller?.abort();
  }

  clear() {
    this.publish({ ...this.state, entries: [] });
  }

  dismissNotice() {
    this.publish({ ...this.state, notice: null });
  }

  private publish(state: LogState) {
    this.state = state;
    this.onChange(state);
  }

  private async poll(generation: number) {
    if (!this.active || generation !== this.generation) return;
    const controller = new AbortController();
    this.controller = controller;
    const timeout = setTimeout(() => controller.abort(), 5000);
    let delay = 1000;
    try {
      // Lọc trên 2.000 dòng đã giữ để đổi nguồn/mức độ mà không đọc lại lịch sử.
      const params = new URLSearchParams({ limit: "500", min_level: "DEBUG" });
      if (this.cursor) params.set("after", this.cursor);
      const response = await this.request(`/api/v1/logs?${params}`, { cache: "no-store", signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const page = parseLogPage(await response.json());
      if (!this.active || generation !== this.generation) return;
      if (page.has_more && page.next_cursor === this.cursor) throw new Error("Cursor không tiến lên.");
      this.cursor = page.next_cursor;
      this.failures = 0;
      this.publish(mergeLogPage(this.state, page));
      delay = page.has_more ? 0 : 1000;
    } catch {
      if (!this.active || generation !== this.generation) return;
      this.publish({ ...this.state, connection: "offline" });
      delay = Math.min(30_000, 1000 * 2 ** Math.min(this.failures++, 5));
    } finally {
      clearTimeout(timeout);
      if (this.active && generation === this.generation) {
        this.timer = setTimeout(() => void this.poll(generation), delay);
      }
    }
  }
}
