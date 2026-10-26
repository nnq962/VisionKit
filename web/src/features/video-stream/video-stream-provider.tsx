"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { VideoStreamStore, browserStreamEnvironment } from "./stream-store";

const VideoStreamContext = createContext<VideoStreamStore | null>(null);

/** Mount once in the root layout. Route subscribers do not own connections. */
export function VideoStreamProvider({ children }: { children: ReactNode }) {
  const [store] = useState(() => new VideoStreamStore(browserStreamEnvironment()));
  useEffect(() => {
    window.addEventListener("online", store.online);
    return () => {
      window.removeEventListener("online", store.online);
      store.dispose();
    };
  }, [store]);
  return <VideoStreamContext.Provider value={store}>{children}</VideoStreamContext.Provider>;
}

export function useVideoStreamStore() {
  const store = useContext(VideoStreamContext);
  if (!store) throw new Error("VideoStreamProvider is required for useVideoStream.");
  return store;
}
