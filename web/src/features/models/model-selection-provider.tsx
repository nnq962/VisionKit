"use client";

import { createContext, useContext, type ReactNode } from "react";
import {
  useModelSelectionState,
  type ModelSelection,
} from "./use-model-selection";
const ModelContext = createContext<ModelSelection | null>(null);
export function ModelSelectionProvider({ children }: { children: ReactNode }) {
  const selection = useModelSelectionState();
  return (
    <ModelContext.Provider value={selection}>{children}</ModelContext.Provider>
  );
}
export function useModelSelection() {
  const context = useContext(ModelContext);
  if (!context) throw new Error("ModelSelectionProvider is required.");
  return context;
}
