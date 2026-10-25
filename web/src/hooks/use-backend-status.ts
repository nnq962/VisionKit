"use client";

import { useEffect, useState } from "react";

export type BackendStatus = "checking" | "online" | "offline";

export function useBackendStatus() {
  const [status, setStatus] = useState<BackendStatus>("checking");

  useEffect(() => {
    let disposed = false;
    let running = false;
    let controller: AbortController | undefined;
    let timer: ReturnType<typeof setTimeout>;

    async function check() {
      if (running || disposed) return;
      clearTimeout(timer);
      running = true;
      controller = new AbortController();
      const timeout = setTimeout(() => controller?.abort(), 3000);
      try {
        const response = await fetch("/api/v1/health", {
          cache: "no-store",
          signal: controller.signal,
        });
        const body = response.ok ? await response.json() : null;
        if (!disposed) setStatus(body?.status === "ok" ? "online" : "offline");
      } catch {
        if (!disposed) setStatus("offline");
      } finally {
        clearTimeout(timeout);
        running = false;
        if (!disposed) timer = setTimeout(() => void check(), 5000);
      }
    }

    function recheck() {
      if (document.visibilityState === "visible") void check();
    }
    void check();
    window.addEventListener("online", recheck);
    window.addEventListener("offline", recheck);
    window.addEventListener("focus", recheck);
    document.addEventListener("visibilitychange", recheck);
    return () => {
      disposed = true;
      clearTimeout(timer);
      controller?.abort();
      window.removeEventListener("online", recheck);
      window.removeEventListener("offline", recheck);
      window.removeEventListener("focus", recheck);
      document.removeEventListener("visibilitychange", recheck);
    };
  }, []);

  return status;
}
