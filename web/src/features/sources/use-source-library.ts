"use client";

import { useEffect, useRef, useState } from "react";
import { listSources } from "./api";
import type { VisionSource } from "./types";

export function useSourceLibrary() {
  const [library, setLibrary] = useState<VisionSource[]>([]);
  const [libraryTotal, setLibraryTotal] = useState(0);
  const [libraryLoading, setLibraryLoading] = useState(true);
  const [libraryError, setLibraryError] = useState("");
  const libraryVersion = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const version = ++libraryVersion.current;
    listSources(0, controller.signal)
      .then((page) => {
        if (version !== libraryVersion.current || controller.signal.aborted)
          return;
        setLibrary(page.items);
        setLibraryTotal(page.total);
      })
      .catch((error) => {
        if (!controller.signal.aborted && version === libraryVersion.current)
          setLibraryError((error as Error).message);
      })
      .finally(() => {
        if (!controller.signal.aborted && version === libraryVersion.current)
          setLibraryLoading(false);
      });
    return () => controller.abort();
  }, []);

  async function refreshLibrary(loadMore = false) {
    const version = ++libraryVersion.current;
    setLibraryLoading(true);
    setLibraryError("");
    try {
      const page = await listSources(loadMore ? library.length : 0);
      if (version !== libraryVersion.current) return;
      setLibrary((items) =>
        loadMore
          ? [
              ...items,
              ...page.items.filter(
                (item) => !items.some((old) => old.id === item.id),
              ),
            ]
          : page.items,
      );
      setLibraryTotal(page.total);
    } catch (error) {
      if (version === libraryVersion.current)
        setLibraryError((error as Error).message);
    } finally {
      if (version === libraryVersion.current) setLibraryLoading(false);
    }
  }

  function remember(saved: VisionSource, isNew = false) {
    libraryVersion.current++;
    setLibraryLoading(false);
    setLibraryError("");
    setLibrary((items) => [
      saved,
      ...items.filter((item) => item.id !== saved.id),
    ]);
    if (isNew) setLibraryTotal((count) => count + 1);
  }

  function forget(id: string) {
    libraryVersion.current++;
    setLibraryLoading(false);
    setLibrary((items) => items.filter((item) => item.id !== id));
    setLibraryTotal((count) => Math.max(0, count - 1));
  }

  return {
    library,
    libraryTotal,
    libraryLoading,
    libraryError,
    refreshLibrary,
    remember,
    forget,
  };
}
