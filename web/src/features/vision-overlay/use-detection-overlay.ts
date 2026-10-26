"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { drawDetections } from "./draw";
import { computeMediaTransform } from "./geometry";
import type { DetectionFrame, OverlayOptions } from "./types";

type MediaElement = HTMLImageElement | HTMLVideoElement;

export const OVERLAY_CANVAS_STYLE: CSSProperties = {
  position: "absolute",
  inset: 0,
  width: "100%",
  height: "100%",
  pointerEvents: "none",
};

/** Canvas annotation độc lập inference/transport; chỉ vẽ khi có kết quả hoặc layout đổi. */
export function useDetectionOverlay({
  result,
  options,
  staleAfterMs = 0,
}: {
  /** undefined để dùng setResult trực tiếp từ WebSocket, null để xoá lớp kết quả. */
  result?: DetectionFrame | null;
  options?: OverlayOptions;
  /** 0 giữ kết quả cho ảnh; luồng live có thể đặt 1500–2000 ms để xoá bbox cũ. */
  staleAfterMs?: number;
} = {}) {
  const [media, setMedia] = useState<MediaElement | null>(null);
  const [canvas, setCanvas] = useState<HTMLCanvasElement | null>(null);
  const frame = useRef<DetectionFrame | null>(null);
  const latest = useRef({ options, staleAfterMs });
  const schedule = useRef<(() => void) | null>(null);
  const expiry = useRef<ReturnType<typeof setTimeout> | null>(null);

  const redraw = useCallback(() => schedule.current?.(), []);
  const setResult = useCallback(
    (next: DetectionFrame | null) => {
      frame.current = next;
      if (expiry.current) clearTimeout(expiry.current);
      expiry.current = null;
      if (next && latest.current.staleAfterMs > 0) {
        expiry.current = setTimeout(() => {
          frame.current = null;
          expiry.current = null;
          redraw();
        }, latest.current.staleAfterMs);
      }
      redraw();
    },
    [redraw],
  );
  const clear = useCallback(() => setResult(null), [setResult]);

  useEffect(() => {
    latest.current = { options, staleAfterMs };
    redraw();
  }, [options, staleAfterMs, redraw]);
  useEffect(() => {
    if (result !== undefined) setResult(result);
  }, [result, setResult]);

  useEffect(() => {
    if (!media || !canvas) return;
    let raf = 0;
    let disposed = false;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    function paint() {
      raf = 0;
      if (disposed || !ctx) return;
      const rect = canvas!.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const width = Math.round(rect.width * dpr),
        height = Math.round(rect.height * dpr);
      if (canvas!.width !== width) canvas!.width = width;
      if (canvas!.height !== height) canvas!.height = height;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, width, height);
      const current = frame.current;
      if (!current || !rect.width || !rect.height) return;
      const element = media!;
      const intrinsicWidth =
        element instanceof HTMLVideoElement
          ? element.videoWidth
          : element.naturalWidth;
      const intrinsicHeight =
        element instanceof HTMLVideoElement
          ? element.videoHeight
          : element.naturalHeight;
      if (element instanceof HTMLImageElement && !element.complete) return;
      const mediaRect = element.getBoundingClientRect();
      const fit = getComputedStyle(element).objectFit;
      const options = latest.current.options ?? {};
      const position = options.position ?? { x: 0.5, y: 0.5 };
      const transform = computeMediaTransform({
        viewportWidth: mediaRect.width,
        viewportHeight: mediaRect.height,
        mediaWidth: intrinsicWidth,
        mediaHeight: intrinsicHeight,
        fit: fit === "cover" || fit === "fill" ? fit : "contain",
        x: mediaRect.left - rect.left,
        y: mediaRect.top - rect.top,
        position: {
          x: options.mirrored ? 1 - position.x : position.x,
          y: position.y,
        },
      });
      if (!transform) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      drawDetections(ctx, current, transform, options);
    }
    function requestPaint() {
      if (!disposed && !raf) raf = requestAnimationFrame(paint);
    }
    schedule.current = requestPaint;
    const observer = new ResizeObserver(requestPaint);
    observer.observe(media);
    observer.observe(canvas);
    const mutations = new MutationObserver(requestPaint);
    mutations.observe(media, {
      attributes: true,
      attributeFilter: ["style", "class", "width", "height"],
    });
    media.addEventListener("load", requestPaint);
    media.addEventListener("loadeddata", requestPaint);
    media.addEventListener("loadedmetadata", requestPaint);
    media.addEventListener("emptied", clear);
    media.addEventListener("error", clear);
    window.addEventListener("resize", requestPaint);
    // Zoom/chuyển màn hình có thể đổi DPR dù kích thước CSS giữ nguyên.
    let resolution: MediaQueryList;
    function watchResolution() {
      resolution?.removeEventListener("change", resolutionChanged);
      resolution = matchMedia(
        `(resolution: ${window.devicePixelRatio || 1}dppx)`,
      );
      resolution.addEventListener("change", resolutionChanged);
    }
    function resolutionChanged() {
      watchResolution();
      requestPaint();
    }
    watchResolution();
    void document.fonts.ready.then(requestPaint);
    requestPaint();
    return () => {
      disposed = true;
      schedule.current = null;
      cancelAnimationFrame(raf);
      observer.disconnect();
      mutations.disconnect();
      media.removeEventListener("load", requestPaint);
      media.removeEventListener("loadeddata", requestPaint);
      media.removeEventListener("loadedmetadata", requestPaint);
      media.removeEventListener("emptied", clear);
      media.removeEventListener("error", clear);
      window.removeEventListener("resize", requestPaint);
      resolution.removeEventListener("change", resolutionChanged);
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    };
  }, [media, canvas, clear]);
  useEffect(
    () => () => {
      if (expiry.current) clearTimeout(expiry.current);
    },
    [],
  );

  return {
    mediaRef: setMedia,
    canvasRef: setCanvas,
    canvasStyle: OVERLAY_CANVAS_STYLE,
    setResult,
    clear,
    redraw,
  };
}
