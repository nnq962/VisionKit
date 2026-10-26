"use client";
import { useState, useSyncExternalStore } from "react";

export type OverlayPreferences = {
  boxes: boolean;
  keypoints: boolean;
  skeleton: boolean;
  labels: boolean;
};
const defaults: OverlayPreferences = {
  boxes: true,
  keypoints: true,
  skeleton: true,
  labels: true,
};
const key = "visionkit:overlay-preferences:v1";
function subscribe(callback: () => void) {
  window.addEventListener("storage", callback);
  window.addEventListener("visionkit:overlay-changed", callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener("visionkit:overlay-changed", callback);
  };
}
export function useOverlayPreferences() {
  const [fallback, setFallback] = useState<OverlayPreferences | null>(null);
  const raw = useSyncExternalStore(
    subscribe,
    () => {
      try {
        return localStorage.getItem(key) ?? "";
      } catch {
        return "";
      }
    },
    () => "",
  );
  let value = { ...defaults };
  try {
    const stored = JSON.parse(raw || "null");
    if (stored)
      for (const name of Object.keys(
        defaults,
      ) as (keyof OverlayPreferences)[]) {
        if (typeof stored[name] === "boolean") value[name] = stored[name];
      }
  } catch {
    /* Bản cũ/hỏng dùng mặc định. */
  }
  value = fallback ?? value;
  return {
    preferences: value,
    update(next: OverlayPreferences) {
      try {
        localStorage.setItem(key, JSON.stringify(next));
        setFallback(null);
        window.dispatchEvent(new Event("visionkit:overlay-changed"));
      } catch {
        setFallback(next);
      }
    },
  };
}
