"use client";

import {
  createContext,
  useContext,
  type ReactNode,
} from "react";
import {
  useSourceSelectionState,
  type SourceSelection,
} from "./use-source-selection";

const SourceContext = createContext<SourceSelection | null>(null);

export function SourceProvider({ children }: { children: ReactNode }) {
  const selection = useSourceSelectionState();
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
