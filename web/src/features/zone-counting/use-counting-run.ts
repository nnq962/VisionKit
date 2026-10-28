"use client";

import { useEffect, useRef, useState } from "react";
import { cancelRun, eventsUrl, finishRun } from "@/features/inference/api";
import type { CountingRun, SourceConfig } from "./types";
import {
  getCountingConfig,
  getCountingProfile,
  getCountingRun,
  stopCountingProfile,
} from "./api";

/** Backend sở hữu run; unmount chỉ dừng observer, không huỷ inference. */
export function useCountingRun(sourceId: string, profileId?: string) {
  const [run, setRun] = useState<CountingRun | null>(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [service, setService] = useState<SourceConfig | null>(null);
  const owner = useRef<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const pending = useRef(false);
  const generation = useRef(0);
  const key = `visionkit:counting-run:${profileId ?? sourceId}`;
  const running = Boolean(run && ["queued", "running"].includes(run.status));
  const active = running || Boolean(service?.enabled);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function restore() {
      const version = generation.current;
      try {
        const signal = AbortSignal.any([
          controller.signal,
          AbortSignal.timeout(10000),
        ]);
        const saved = profileId
          ? await getCountingProfile(profileId, signal)
          : await getCountingConfig(sourceId, signal);
        if (controller.signal.aborted || version !== generation.current) return;
        setService(saved);
        owner.current = profileId ?? saved.owner_profile_id ?? null;
        let localId: string | null = null;
        try {
          localId = localStorage.getItem(key);
        } catch {
          /* Backend vẫn là nguồn khôi phục chính. */
        }
        const id =
          saved.current_run_id ?? (profileId || saved.stale ? null : localId);
        if (id) {
          const record = (await getCountingRun(
            id,
            AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]),
          )) as CountingRun;
          if (
            !controller.signal.aborted &&
            version === generation.current &&
            record.counting
          ) {
            setRun((current) =>
              current?.id === record.id &&
              current.updated_at >= record.updated_at
                ? current
                : record,
            );
            setNow(Date.now());
            setError("");
          }
        } else if (
          !controller.signal.aborted &&
          version === generation.current
        ) {
          setRun(null);
          setError("");
        }
      } catch (reason) {
        if (!controller.signal.aborted) {
          const status = (reason as Error & { status?: number }).status;
          if (status === 404 || status === 410) {
            try {
              localStorage.removeItem(key);
            } catch {
              /* Lượt đã được dọn/hết hạn, vẫn có thể tạo lượt mới. */
            }
          } else setError((reason as Error).message);
        }
      } finally {
        if (!controller.signal.aborted) {
          setReady(true);
          timer = setTimeout(() => void restore(), 1500);
        }
      }
    }
    void restore();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [key, sourceId, profileId]);
  useEffect(() => {
    if (!run?.id || !running) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const id = run.id;
    const socket = new WebSocket(eventsUrl(id));
    function accept(record: CountingRun) {
      if (controller.signal.aborted || record.id !== id || !record.counting)
        return;
      setRun((current) =>
        current?.id !== id || current.updated_at >= record.updated_at
          ? current
          : record,
      );
      setError("");
      setNow(Date.now());
    }
    socket.onmessage = (event) => {
      try {
        accept(JSON.parse(event.data) as CountingRun);
      } catch {
        /* HTTP dự phòng phục hồi trạng thái khi sự kiện không đọc được. */
      }
    };
    async function poll() {
      try {
        const record = (await getCountingRun(
          id,
          AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]),
        )) as CountingRun;
        accept(record);
      } catch (reason) {
        if (!controller.signal.aborted) setError((reason as Error).message);
      } finally {
        if (!controller.signal.aborted)
          timer = setTimeout(() => void poll(), 1000);
      }
    }
    // Giống YOLO pipeline: WebSocket nhận snapshot, HTTP kiểm tra dự phòng.
    timer = setTimeout(() => void poll(), 500);
    const clock = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      controller.abort();
      clearTimeout(timer);
      clearInterval(clock);
      socket.close();
    };
  }, [run?.id, running]);
  async function start(create: () => Promise<CountingRun>) {
    if (pending.current || active) return;
    pending.current = true;
    generation.current++;
    setBusy(true);
    setError("");
    try {
      const next = await create();
      setRun(next);
      setNow(Date.now());
      try {
        localStorage.setItem(key, next.id);
      } catch {
        setError(
          "Lượt đếm đã chạy nhưng trình duyệt không lưu được mã khôi phục.",
        );
      }
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  async function stop() {
    if ((!run && !owner.current) || pending.current) return;
    pending.current = true;
    generation.current++;
    setBusy(true);
    setError("");
    try {
      if (owner.current) {
        const stopped = await stopCountingProfile(owner.current);
        setService(stopped);
        if (stopped.current_run_id)
          setRun(await getCountingRun(stopped.current_run_id));
      } else if (run) {
        setRun((await cancelRun(run.id)) as CountingRun);
      }
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  async function reset() {
    if (pending.current || active) return false;
    pending.current = true;
    generation.current++;
    setBusy(true);
    setError("");
    try {
      if (run) await finishRun(run.id);
      try {
        localStorage.removeItem(key);
      } catch {
        /* Có thể thiết lập lại trong phiên hiện tại. */
      }
      setRun(null);
      return true;
    } catch (reason) {
      setError((reason as Error).message);
      return false;
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  const stale = Boolean(
    active &&
    run?.source_kind === "stream" &&
    (!run.result || now - Date.parse(run.updated_at) > 3000),
  );
  return {
    run,
    service,
    ready,
    active,
    running,
    busy,
    error,
    stale,
    start,
    stop,
    reset,
  };
}
