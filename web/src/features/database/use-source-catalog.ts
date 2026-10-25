"use client";

import { useEffect, useState } from "react";
import { listSources } from "@/features/sources/api";
import type { SourceKind, VisionSource } from "@/features/sources/types";

export function useSourceCatalog(revision: string) {
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState<SourceKind | "all">("all");
  const [page, setPage] = useState(0);
  const [query, setQuery] = useState("");
  const [result, setResult] = useState({
    items: [] as VisionSource[],
    total: 0,
    key: "",
    error: "",
  });
  const [retry, setRetry] = useState(0);
  const limit = 20;
  const key = JSON.stringify([query, kind, page, revision, retry]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(search.trim());
      setPage(0);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    const controller = new AbortController();
    listSources(page * limit, controller.signal, {
      q: query,
      kind: kind === "all" ? undefined : kind,
      limit,
    })
      .then((data) => {
        if (controller.signal.aborted) return;
        if (page > 0 && data.items.length === 0) {
          setPage(page - 1);
          return;
        }
        setResult({ ...data, key, error: "" });
      })
      .catch((reason: Error) => {
        if (!controller.signal.aborted)
          setResult((old) => ({ ...old, key, error: reason.message }));
      });
    return () => controller.abort();
  }, [query, kind, page, key]);

  return {
    ...result,
    search,
    kind,
    page,
    limit,
    loading: result.key !== key || search.trim() !== query,
    setSearch,
    setKind(value: SourceKind | "all") {
      setKind(value);
      setPage(0);
    },
    setPage,
    refresh() {
      setRetry((value) => value + 1);
    },
  };
}
