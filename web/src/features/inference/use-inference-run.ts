"use client";
import { useEffect, useRef, useState } from "react";
import { restoreRun } from "./restore-run";
import type { VisionSource } from "@/features/sources/types";
import type { YoloParameters } from "@/features/pipelines/yolo/types";
import {
  cancelRun,
  finishRun,
  eventsUrl,
  getRun,
  startRun,
  type InferenceRun,
} from "./api";

export function useInferenceRun(
  source: VisionSource | null,
  modelId: string | null,
  parameters: YoloParameters,
) {
  const [run, setRun] = useState<InferenceRun | null>(null);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const [finishing, setFinishing] = useState(false);
  const [stopping, setStopping] = useState(false);
  const pending = useRef(false);
  const mounted = useRef(true);
  const upload = useRef<AbortController | null>(null);
  const restoring = useRef<AbortController | null>(null);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      upload.current?.abort();
    };
  }, []);
  const selectionKey = `${source?.id ?? ""}:${modelId ?? ""}:${JSON.stringify(parameters)}`;
  useEffect(() => {
    const controller = new AbortController();
    restoring.current = controller;
    let id: string | null = null;
    try {
      id = sessionStorage.getItem(`visionkit:run:${selectionKey}`);
    } catch {
      /* sessionStorage best effort. */
    }
    if (id)
      void restoreRun(
        () => getRun(id!, controller.signal),
        source?.kind,
        controller.signal,
      )
        .then((next) => {
          if (next && !controller.signal.aborted) setRun(next);
        })
        .catch(() => {});
    return () => controller.abort();
  }, [selectionKey, source?.kind]);
  const active = Boolean(run && ["queued", "running"].includes(run.status));
  useEffect(() => {
    if (!run?.id || !active) return;
    const id = run.id;
    const controller = new AbortController();
    // HTTP poll dự phòng khi proxy không chuyển tiếp được WebSocket; DB là nguồn sự thật.
    let timer: ReturnType<typeof setTimeout>;
    const socket = new WebSocket(eventsUrl(id));
    socket.onmessage = (event) => {
      try {
        const next = JSON.parse(event.data) as InferenceRun;
        if (next.id === id && !controller.signal.aborted)
          setRun((current) =>
            current?.id === next.id && current.updated_at >= next.updated_at
              ? current
              : next,
          );
      } catch {
        /* HTTP poll sẽ phục hồi trạng thái. */
      }
    };
    async function poll() {
      try {
        const next = await getRun(id, controller.signal);
        if (!controller.signal.aborted) {
          setError("");
          setRun((current) =>
            current?.id === next.id && current.updated_at >= next.updated_at
              ? current
              : next,
          );
        }
      } catch (reason) {
        if (!controller.signal.aborted) setError((reason as Error).message);
      } finally {
        if (!controller.signal.aborted)
          timer = setTimeout(() => void poll(), 1000);
      }
    }
    timer = setTimeout(() => void poll(), 500);
    return () => {
      controller.abort();
      clearTimeout(timer);
      socket.close();
    };
  }, [run?.id, active]);
  return {
    run,
    error,
    starting,
    stopping,
    finishing,
    active,
    async finish(complete: () => Promise<void>) {
      if (!run || active || pending.current) return;
      pending.current = true;
      setFinishing(true);
      setError("");
      restoring.current?.abort();
      try {
        await finishRun(run.id);
        try { sessionStorage.removeItem(`visionkit:run:${selectionKey}`); } catch {}
        await complete();
        if (mounted.current) setRun(null);
      } catch (reason) {
        if (mounted.current) setError((reason as Error).message);
      } finally {
        pending.current = false;
        if (mounted.current) setFinishing(false);
      }
    },
    async start() {
      if (pending.current || active || !source || !modelId) return;
      restoring.current?.abort();
      pending.current = true;
      setStarting(true);
      setError("");
      setRun(null);
      const controller = new AbortController();
      upload.current = controller;
      try {
        const next = await startRun(
          source,
          modelId,
          parameters,
          controller.signal,
        );
        try {
          sessionStorage.setItem(`visionkit:run:${selectionKey}`, next.id);
        } catch {
          /* Result vẫn xem được trong lượt hiện tại. */
        }
        if (mounted.current) setRun(next);
      } catch (reason) {
        if (mounted.current) setError((reason as Error).message);
      } finally {
        pending.current = false;
        if (mounted.current) setStarting(false);
      }
    },
    async stop() {
      if (!run || stopping) return;
      setStopping(true);
      try {
        const next = await cancelRun(run.id);
        if (mounted.current) setRun(next);
      } catch (reason) {
        if (mounted.current) setError((reason as Error).message);
      } finally {
        if (mounted.current) setStopping(false);
      }
    },
  };
}
