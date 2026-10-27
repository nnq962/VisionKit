/** Khôi phục lượt còn chạy; video đã kết thúc trở về preview ban đầu khi vào lại bước 4. */
export async function restoreRun<T extends { status: string }>(
  load: () => Promise<T>,
  sourceKind: string | undefined,
  signal: AbortSignal,
): Promise<T | null> {
  const run = await load();
  if (signal.aborted) return null;
  if (["video", "youtube"].includes(sourceKind ?? "") && run.status !== "queued" && run.status !== "running") return null;
  return run;
}
