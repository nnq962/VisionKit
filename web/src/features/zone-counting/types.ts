import type { InferenceRun } from "@/features/inference/api";

export const medicalClasses = [
  ["person", "Người"],
  ["wheelchair", "Xe lăn"],
  ["hospital stretcher", "Cáng bệnh viện"],
  ["hospital bed", "Giường bệnh"],
  ["medical trolley", "Xe đẩy y tế"],
  ["IV pole", "Cọc truyền dịch"],
] as const;
export const defaultCountingClasses = medicalClasses.map(
  ([key]) => key,
) as string[];

export function countingClassLabel(key: string): string {
  return medicalClasses.find(([name]) => name === key)?.[1] ?? key;
}
export type Point = [number, number];
export type CountingZone = {
  id: string;
  name: string;
  color: string;
  points: Point[];
  classes: string[];
};
export type CountingConfig = {
  version: 1;
  classes?: string[];
  reference_width: number;
  reference_height: number;
  zones: CountingZone[];
};
export type CountResult = {
  valid: boolean;
  reason: string | null;
  frame_id: number | null;
  timestamp_ms: number | null;
  regions: {
    id: string;
    name: string;
    color: string;
    total: number;
    counts: Partial<Record<string, number>>;
  }[];
};
export type CountingOptions = {
  conf: number;
  iou: number;
  device: string;
  max_fps: number;
};
export type MonitorSettings = {
  model_id: string;
  options: CountingOptions;
  duration_seconds: number;
  continuous?: boolean;
  auto_start?: boolean;
};
export type CountingRun = InferenceRun & {
  options: CountingOptions;
  counting: CountingConfig;
  counts: CountResult | null;
};
export type SourceConfig = {
  source_signature: string;
  config: CountingConfig | null;
  stale: boolean;
  monitor?: MonitorSettings | null;
  current_run_id?: string | null;
  owner_profile_id?: string | null;
  enabled?: boolean;
  runtime?: {
    phase?: "running" | "retrying" | "blocked";
    error?: string | null;
    retry_at?: string | null;
  };
};

export type CountingProfile = SourceConfig & {
  id: string;
  name: string;
  source_id: string;
  config: CountingConfig;
  monitor: MonitorSettings;
  created_at: string;
  updated_at: string;
};
export const profileSelectionKey = "visionkit:counting-profile";
