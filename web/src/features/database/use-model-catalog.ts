"use client";

import { useEffect, useRef, useState } from "react";
import {
  configureModel,
  getLibrary,
  inspectModel,
  type StoredModel,
} from "@/features/models/api";
import type { ModelTask } from "@/features/models/catalog";

export function useModelCatalog() {
  const [items, setItems] = useState<StoredModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [revision, setRevision] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [inspecting, setInspecting] = useState(false);
  const pending = useRef(false);
  const mounted = useRef(true);
  const selected = items.find((item) => item.id === selectedId) ?? null;

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const models = await getLibrary(controller.signal);
        if (controller.signal.aborted) return;
        setItems(models);
        setError("");
      } catch (reason) {
        if (!controller.signal.aborted) setError((reason as Error).message);
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
          timer = setTimeout(() => void load(), 4000);
        }
      }
    }
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [revision]);
  useEffect(() => {
    const refresh = () => setRevision((value) => value + 1);
    window.addEventListener("focus", refresh);
    window.addEventListener("visionkit:models-changed", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
      window.removeEventListener("visionkit:models-changed", refresh);
    };
  }, []);

  function replace(model: StoredModel) {
    if (mounted.current)
      setItems((items) =>
        items.map((item) => (item.id === model.id ? model : item)),
      );
    window.dispatchEvent(new Event("visionkit:models-changed"));
  }
  async function retryInspection() {
    if (!selectedId || pending.current) return;
    pending.current = true;
    setInspecting(true);
    setActionError("");
    try {
      replace(await inspectModel(selectedId));
    } catch (reason) {
      if (mounted.current) setActionError((reason as Error).message);
    } finally {
      pending.current = false;
      if (mounted.current) setInspecting(false);
    }
  }
  async function configure(
    family: "yolo" | "yoloe",
    task: ModelTask,
  ): Promise<boolean> {
    if (!selectedId || pending.current) return false;
    pending.current = true;
    setInspecting(true);
    setActionError("");
    try {
      replace(await configureModel(selectedId, family, task));
      return true;
    } catch (reason) {
      if (mounted.current) setActionError((reason as Error).message);
      return false;
    } finally {
      pending.current = false;
      if (mounted.current) setInspecting(false);
    }
  }
  return {
    items,
    selected,
    loading,
    error,
    actionError,
    inspecting,
    retryInspection,
    configure,
    refresh() {
      setLoading(true);
      setRevision((value) => value + 1);
    },
    open(id: string) {
      setSelectedId(id);
      setActionError("");
    },
    close() {
      setSelectedId(null);
      setActionError("");
    },
  };
}
