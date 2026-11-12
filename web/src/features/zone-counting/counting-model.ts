import type { StoredModel } from "@/features/models/api";

export function usesCountingPrompts(model: StoredModel | null): boolean {
  return Boolean(model?.familyId.startsWith("yoloe"));
}

export function countingModelClasses(model: StoredModel | null): string[] {
  const names = Object.entries(model?.inspection.metadata?.names ?? {})
    .filter(([id, name]) => /^\d+$/.test(id) && name.trim())
    .sort(([a], [b]) => Number(a) - Number(b))
    .map(([, name]) => name);
  return [
    ...new Map(names.map((name) => [name.toLocaleLowerCase(), name])).values(),
  ];
}

export function supportsCounting(model: StoredModel): boolean {
  return (
    model.familyId.startsWith("yolo") &&
    ["detect", "segment"].includes(model.task ?? "") &&
    ["ready", "manual"].includes(model.inspection.status) &&
    (usesCountingPrompts(model)
      ? model.format === "pt"
      : countingModelClasses(model).length > 0)
  );
}

export function reconcileCountingClasses(
  current: string[],
  available: string[],
): string[] {
  const kept = current.filter((name) => available.includes(name));
  return kept.length ? kept : available;
}
