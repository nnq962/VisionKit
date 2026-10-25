"use client";

import { useEffect, useRef, useState } from "react";
import type { ModelFamily, ModelVariant } from "./catalog";
import {
  cancelDownload,
  deleteModel,
  getCatalog,
  getDownloads,
  getLibrary,
  startDownload,
  type ModelDownload,
  type StoredModel,
} from "./api";

export function useModelDownloads() {
  const [families, setFamilies] = useState<ModelFamily[]>([]);
  const [saved, setSaved] = useState<StoredModel[]>([]);
  const [history, setHistory] = useState<ModelDownload[]>([]);
  const [ready, setReady] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState<string[]>([]);
  const pending = useRef(new Set<string>());
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let catalogLoaded = false;
    async function poll() {
      if (controller.signal.aborted) return;
      let active = false;
      try {
        if (!catalogLoaded) {
          const catalog = await getCatalog(controller.signal);
          if (controller.signal.aborted) return;
          setFamilies(catalog.families);
          catalogLoaded = true;
        }
        const [models, downloads] = await Promise.all([
          getLibrary(controller.signal),
          getDownloads(controller.signal),
        ]);
        if (controller.signal.aborted) return;
        setSaved(models);
        setHistory(downloads);
        setReady(true);
        setLoadError("");
        active = downloads.some((job) =>
          ["queued", "downloading"].includes(job.status),
        );
      } catch (error) {
        if (!controller.signal.aborted) {
          setLoadError((error as Error).message);
          setReady(false);
        }
      }
      if (!controller.signal.aborted)
        timer = setTimeout(() => void poll(), active ? 700 : 4000);
    }
    void poll();
    return () => {
      mounted.current = false;
      controller.abort();
      clearTimeout(timer);
    };
  }, [revision]);

  async function act(key: string, operation: () => Promise<void>) {
    if (pending.current.has(key)) return;
    pending.current.add(key);
    setBusy([...pending.current]);
    setActionError("");
    try {
      await operation();
    } catch (error) {
      if (mounted.current) setActionError((error as Error).message);
    } finally {
      pending.current.delete(key);
      if (mounted.current) {
        setBusy([...pending.current]);
        setRevision((value) => value + 1);
      }
    }
  }
  const jobs: Record<string, ModelDownload> = {};
  for (const job of history)
    if (!jobs[job.variant.id]) jobs[job.variant.id] = job;
  return {
    families,
    saved,
    jobs,
    history,
    busy,
    ready,
    error: actionError || loadError,
    notice,
    refresh() {
      setActionError("");
      setRevision((value) => value + 1);
    },
    download(variant: ModelVariant) {
      void act(variant.id, async () => {
        const job = await startDownload(variant);
        if (mounted.current) {
          setHistory((items) => [
            job,
            ...items.filter((item) => item.jobId !== job.jobId),
          ]);
          setNotice(`Bắt đầu tải ${variant.filename}.`);
        }
      });
    },
    cancel(id: string) {
      const job = jobs[id];
      if (!job) return;
      void act(id, async () => {
        await cancelDownload(job.jobId);
      });
    },
    remove(id: string) {
      void act(id, async () => {
        await deleteModel(id);
        if (mounted.current) setNotice("Đã xoá model.");
      });
    },
  };
}
