"use client";

import { useState, useSyncExternalStore } from "react";
import type { StoredModel } from "@/features/models/api";
import { fixedImageSize, parametersForModel } from "./parameters";
import type { YoloParameters } from "./types";

function subscribe(callback: () => void) {
  window.addEventListener("storage", callback);
  window.addEventListener("visionkit:parameters-changed", callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener("visionkit:parameters-changed", callback);
  };
}

export function usePipelineParameters(model: StoredModel | null) {
  const id = model?.id ?? "";
  const key = `visionkit:yolo-parameters:${id}`;
  const [fallback, setFallback] = useState<{
    id: string;
    value: YoloParameters;
  } | null>(null);
  const [writeError, setWriteError] = useState("");
  const raw = useSyncExternalStore(
    subscribe,
    () => {
      try {
        return localStorage.getItem(key) ?? "";
      } catch {
        return "unavailable";
      }
    },
    () => "",
  );
  let value = parametersForModel(model);
  let readError = "";
  try {
    const saved = JSON.parse(raw || "null");
    if (saved && typeof saved === "object") {
      for (const name of [
        "confidence",
        "iou",
        "imageSize",
        "device",
        "maxDet",
        "vidStride",
        "liveFps",
        "liveMinutes",
      ] as const) {
        if (typeof saved[name] === "string") value[name] = saved[name];
      }
      if (["all", "selected"].includes(saved.classMode))
        value.classMode = saved.classMode;
      if (Array.isArray(saved.classes))
        value.classes = saved.classes.filter(
          (item: unknown) => typeof item === "string",
        );
      if (typeof saved.agnosticNms === "boolean")
        value.agnosticNms = saved.agnosticNms;
    }
  } catch {
    readError = "Không khôi phục được thông số đã lưu.";
  }
  if (fallback?.id === id) value = fallback.value;
  return {
    parameters: {
      ...value,
      imageSize: fixedImageSize(model) ?? value.imageSize,
    },
    storageError: writeError || readError,
    update(next: YoloParameters) {
      try {
        localStorage.setItem(key, JSON.stringify(next));
        setFallback(null);
        setWriteError("");
        window.dispatchEvent(new Event("visionkit:parameters-changed"));
      } catch {
        setFallback({ id, value: next });
        setWriteError("Không giữ được thông số sau reload.");
      }
    },
  };
}
