"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { INITIAL_LOG_STATE, LogStream } from "./log-stream";

export function useRuntimeLogs(open: boolean, paused: boolean) {
  const [state, setState] = useState(INITIAL_LOG_STATE);
  const stream = useRef<LogStream | null>(null);

  useEffect(() => {
    const reader = stream.current ?? new LogStream(setState);
    stream.current = reader;
    function sync() {
      if (open && !paused && document.visibilityState === "visible") reader.start();
      else reader.stop();
    }
    sync();
    document.addEventListener("visibilitychange", sync);
    window.addEventListener("online", sync);
    return () => {
      reader.stop();
      document.removeEventListener("visibilitychange", sync);
      window.removeEventListener("online", sync);
    };
  }, [open, paused]);

  const clear = useCallback(() => stream.current?.clear(), []);
  const dismissNotice = useCallback(() => stream.current?.dismissNotice(), []);
  return { ...state, clear, dismissNotice };
}
