"use client";

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  type ReactNode,
} from "react";
import { usePathname } from "next/navigation";
import {
  useSourceSelectionState,
  type SourceSelection,
} from "./use-source-selection";

const SourceContext = createContext<SourceSelection | null>(null);

export function SourceProvider({ children }: { children: ReactNode }) {
  const selection = useSourceSelectionState();
  const pathname = usePathname();
  const stopCamera = useRef(selection.stopCamera);
  useEffect(() => {
    stopCamera.current = selection.stopCamera;
  });
  useEffect(() => {
    if (pathname !== "/pipelines/yolo") stopCamera.current();
  }, [pathname]);
  return (
    <SourceContext.Provider value={selection}>
      {children}
    </SourceContext.Provider>
  );
}

export function useSourceSelection() {
  const context = useContext(SourceContext);
  if (!context)
    throw new Error("SourceProvider is required for the source picker.");
  return context;
}
