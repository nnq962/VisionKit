"use client";

import { useEffect, useRef } from "react";
import { drawDetections } from "@/features/vision-overlay/draw";
import { computeMediaTransform } from "@/features/vision-overlay/geometry";
import type { DetectionFrame, OverlayOptions } from "@/features/vision-overlay/types";

type Frame = { src: string; result: DetectionFrame | null };

/** Giữ một canvas: decode ngoài màn hình rồi vẽ ảnh và bbox trong cùng một lượt. */
export function WebcamRunPreview({
  src,
  result,
  options,
  active,
  name,
}: Frame & { options: OverlayOptions; active: boolean; name: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const latest = useRef({ src, result, options, active });
  const refresh = useRef<(() => void) | null>(null);

  useEffect(() => {
    latest.current = { src, result, options, active };
    refresh.current?.();
  }, [src, result, options, active]);

  useEffect(() => {
    const element = canvas.current;
    const ctx = element?.getContext("2d");
    if (!element || !ctx) return;
    let disposed = false;
    let loading = false;
    let image: HTMLImageElement | null = null;
    let displayed: Frame | null = null;
    let displayedAt = 0;
    let attempted = "";
    let raf = 0;
    let expiry: ReturnType<typeof setTimeout>;

    function paint() {
      raf = 0;
      if (disposed || !image || !element || !ctx) return;
      const rect = element.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const width = Math.round(rect.width * dpr);
      const height = Math.round(rect.height * dpr);
      if (!width || !height) return;
      const transform = computeMediaTransform({
        viewportWidth: rect.width,
        viewportHeight: rect.height,
        mediaWidth: image.naturalWidth,
        mediaHeight: image.naturalHeight,
      });
      if (!transform) return;
      if (element.width !== width) element.width = width;
      if (element.height !== height) element.height = height;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = "#09090b";
      ctx.fillRect(0, 0, rect.width, rect.height);
      ctx.drawImage(image, transform.x, transform.y, transform.width, transform.height);
      if (displayed?.result && (!latest.current.active || Date.now() - displayedAt < 2000)) {
        drawDetections(ctx, displayed.result, transform, latest.current.options);
      }
    }

    function schedule() {
      if (!disposed && !raf) raf = requestAnimationFrame(paint);
    }

    async function loadNewest() {
      if (loading || disposed) return;
      loading = true;
      try {
        // Coalesce updates while decoding; keep the displayed frame on slow/error responses.
        while (!disposed && latest.current.src && latest.current.src !== attempted) {
          const next = { src: latest.current.src, result: latest.current.result };
          attempted = next.src;
          const pending = new Image();
          pending.src = next.src;
          try {
            await pending.decode();
            if (disposed) return;
            image = pending;
            displayed = next;
            displayedAt = Date.now();
            clearTimeout(expiry);
            expiry = setTimeout(schedule, 2000);
            schedule();
          } catch {
            // The next frame retries naturally. Never clear the last successfully drawn image.
          }
        }
      } finally {
        loading = false;
      }
    }

    refresh.current = () => { schedule(); void loadNewest(); };
    const observer = new ResizeObserver(schedule);
    observer.observe(element);
    window.addEventListener("resize", schedule);
    void loadNewest();
    return () => {
      disposed = true;
      refresh.current = null;
      observer.disconnect();
      window.removeEventListener("resize", schedule);
      clearTimeout(expiry);
      cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <div className="space-y-3">
      <canvas ref={canvas} role="img" aria-label={name} className="block aspect-video w-full rounded-lg bg-muted" />
      <p className="text-xs text-muted-foreground">
        Hình từ đúng frame AI đang xử lý; preview theo nhịp AI. Webcam chỉ dành cho trình duyệt chạy cùng máy với server.
      </p>
    </div>
  );
}
