type TimedResult = { timestampMs?: number };

/** Ghép kết quả theo đồng hồ video; không điều khiển tốc độ hoặc vị trí phát. */
export class VideoResultTimeline<T extends TimedResult> {
  private pending: T[] = [];
  private current: T | null = null;
  private readonly maxAgeMs: number;
  private readonly capacity: number;

  constructor(maxAgeMs = 150, capacity = 512) {
    this.maxAgeMs = maxAgeMs;
    this.capacity = capacity;
  }

  push(result: T, mediaTimeMs: number): void {
    const time = result.timestampMs;
    if (
      time === undefined || !Number.isFinite(time) || time < 0 ||
      time < mediaTimeMs - this.maxAgeMs
    ) return;
    // Poll và WebSocket có thể gửi trùng hoặc không đúng thứ tự.
    const index = this.pending.findIndex((item) => item.timestampMs! >= time);
    if (index < 0) this.pending.push(result);
    else if (this.pending[index].timestampMs === time) this.pending[index] = result;
    else this.pending.splice(index, 0, result);
    // Giữ các frame sắp tới; không tăng bộ nhớ vô hạn khi tab bị ẩn/video buffering.
    if (this.pending.length > this.capacity) this.pending.length = this.capacity;
  }

  at(mediaTimeMs: number): T | null {
    while (this.pending.length && this.pending[0].timestampMs! <= mediaTimeMs) {
      const next = this.pending.shift()!;
      if (!this.current || next.timestampMs! >= this.current.timestampMs!) {
        this.current = next;
      }
    }
    if (
      this.current && (mediaTimeMs < this.current.timestampMs! ||
        mediaTimeMs - this.current.timestampMs! > this.maxAgeMs)
    ) this.current = null;
    return this.current;
  }
}
