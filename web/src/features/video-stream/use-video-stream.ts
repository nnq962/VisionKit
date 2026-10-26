"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";
import { EMPTY_STREAM } from "./stream-store";
import { useVideoStreamStore } from "./video-stream-provider";

/** Saved RTSP source ID only. Unmounting keeps it alive until stop() or app exit. */
export function useVideoStream(
  sourceId: string | null,
  { autoConnect = true } = {},
) {
  const store = useVideoStreamStore();
  const subscribe = useCallback(
    (listener: () => void) =>
      sourceId ? store.subscribe(sourceId, listener) : () => {},
    [store, sourceId],
  );
  const getSnapshot = useCallback(
    () => (sourceId ? store.snapshot(sourceId) : EMPTY_STREAM),
    [store, sourceId],
  );
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, () => EMPTY_STREAM);
  useEffect(() => {
    if (sourceId && autoConnect && store.snapshot(sourceId).status === "idle") {
      store.start(sourceId);
    }
  }, [store, sourceId, autoConnect]);
  const connect = useCallback(() => {
    if (sourceId) store.start(sourceId);
  }, [store, sourceId]);
  const reconnect = useCallback(() => {
    if (sourceId) store.reconnect(sourceId);
  }, [store, sourceId]);
  const stop = useCallback(() => {
    if (sourceId) store.stop(sourceId);
  }, [store, sourceId]);

  return { ...snapshot, connect, reconnect, stop };
}
