"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRightIcon,
  CameraIcon,
  Clock3Icon,
  HeartPulseIcon,
  PlayIcon,
  RefreshCwIcon,
  Settings2Icon,
  SquareIcon,
} from "lucide-react";
import { WorkspacePage, WorkspaceSection } from "@/components/workspace-page";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { getLibrary, type StoredModel } from "@/features/models/api";
import { listSources } from "@/features/sources/api";
import type { VisionSource } from "@/features/sources/types";
import { OverlayControls } from "@/features/inference/components/overlay-controls";
import { useOverlayPreferences } from "@/features/inference/use-overlay-preferences";
import { RunMetrics } from "@/features/inference/components/run-metrics";
import {
  getCountingProfile,
  listCountingProfiles,
  startCountingProfile,
} from "./api";
import { CountingPreview } from "./counting-preview";
import { useCountingRun } from "./use-counting-run";
import {
  countingClassLabel,
  defaultCountingClasses,
  type CountingProfile,
  profileSelectionKey,
} from "./types";
import { regionTotals } from "./monitoring";

const noop = () => {};

/** Màn giám sát dùng API cấu hình và observer lượt AI thật, không tự tạo run khi mount. */
export function CountingMonitorPage() {
  const [sources, setSources] = useState<VisionSource[]>([]);
  const [models, setModels] = useState<StoredModel[]>([]);
  const [profileId, setProfileId] = useState("");
  const [profiles, setProfiles] = useState<CountingProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    async function allSources(kind: "stream" | "video") {
      const items: VisionSource[] = [];
      let total = 1;
      while (items.length < total) {
        const page = await listSources(items.length, controller.signal, {
          kind,
          limit: 100,
        });
        items.push(...page.items);
        total = page.total;
        if (!page.items.length) break;
      }
      return items;
    }
    void Promise.all([
      allSources("stream"),
      allSources("video"),
      getLibrary(controller.signal),
      listCountingProfiles(controller.signal),
    ])
      .then(([streams, videos, library, savedProfiles]) => {
        if (controller.signal.aborted) return;
        const all = [...streams, ...videos];
        setSources(all);
        setProfiles(savedProfiles);
        setModels(
          library.filter(
            (item) =>
              item.familyId.startsWith("yoloe") &&
              item.format === "pt" &&
              ["ready", "manual"].includes(item.inspection.status) &&
              ["detect", "segment"].includes(item.task ?? ""),
          ),
        );
        let savedId = "";
        try {
          savedId = localStorage.getItem(profileSelectionKey) ?? "";
        } catch {
          /* Có thể chọn lại thủ công. */
        }
        setProfileId((current) =>
          savedProfiles.some((item) => item.id === current)
            ? current
            : savedProfiles.some((item) => item.id === savedId)
              ? savedId
              : (savedProfiles[0]?.id ?? ""),
        );
        setError("");
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError((reason as Error).message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [revision]);
  useEffect(() => {
    if (!profileId) return;
    try {
      localStorage.setItem(profileSelectionKey, profileId);
    } catch {
      /* Giữ lựa chọn trong phiên hiện tại. */
    }
  }, [profileId]);
  const profile = profiles.find((item) => item.id === profileId);
  const source = sources.find((item) => item.id === profile?.source_id);
  return (
    <WorkspacePage
      title="Counting Monitor"
      description="Theo dõi số đếm theo vùng."
    >
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="w-full space-y-2 sm:w-80">
          <Label htmlFor="monitor-profile">Cấu hình giám sát</Label>
          <Select
            value={profileId}
            onValueChange={setProfileId}
            disabled={loading}
          >
            <SelectTrigger id="monitor-profile" className="w-full">
              <SelectValue placeholder="Chọn cấu hình đã lưu" />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {profiles.map((item) => (
                  <SelectItem key={item.id} value={item.id}>
                    {item.name}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="icon"
            aria-label="Làm mới cấu hình"
            onClick={() => setRevision((value) => value + 1)}
          >
            <RefreshCwIcon />
          </Button>
          <Button variant="outline" asChild>
            <Link href="/counting/configure">
              <Settings2Icon />
              Cấu hình
            </Link>
          </Button>
        </div>
      </div>
      {error && (
        <div
          role="alert"
          className="rounded-lg border border-destructive/30 p-4 text-sm text-destructive"
        >
          {error}
        </div>
      )}
      {loading ? (
        <p role="status" className="text-sm text-muted-foreground">
          Đang tải cấu hình…
        </p>
      ) : source && profile ? (
        <MonitorWorkspace
          key={profile.id}
          profile={profile}
          source={source}
          models={models}
        />
      ) : (
        <WorkspaceSection
          title={
            profile ? "Nguồn cấu hình không còn khả dụng" : "Chưa có cấu hình"
          }
          titleId="monitor-empty-heading"
        >
          <div className="flex flex-col items-center gap-4 py-8 text-center">
            <CameraIcon className="size-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              {profile
                ? "Chọn lại nguồn trong cấu hình."
                : "Tạo cấu hình để bắt đầu giám sát."}
            </p>
            <Button asChild>
              <Link href="/counting/configure">
                {profile ? "Sửa cấu hình" : "Tạo cấu hình"}
                <ArrowRightIcon />
              </Link>
            </Button>
          </div>
        </WorkspaceSection>
      )}
    </WorkspacePage>
  );
}

function MonitorWorkspace({
  profile,
  source,
  models,
}: {
  profile: CountingProfile;
  source: VisionSource;
  models: StoredModel[];
}) {
  const session = useCountingRun(source.id, profile.id);
  const { run, active } = session;
  const { preferences, update } = useOverlayPreferences();
  const [configuration, setConfiguration] = useState<CountingProfile | null>(
    profile,
  );
  const [loading, setLoading] = useState(true);
  const [configError, setConfigError] = useState("");
  const [revision, setRevision] = useState(0);
  const [showZones, setShowZones] = useState(true);
  const [anchors, setAnchors] = useState(true);
  const [connected, setConnected] = useState(source.kind !== "stream");
  useEffect(() => {
    const controller = new AbortController();
    void getCountingProfile(profile.id, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) {
          setConfiguration(value);
          setConfigError("");
        }
      })
      .catch((reason) => {
        if (!controller.signal.aborted)
          setConfigError((reason as Error).message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [profile.id, revision]);
  const settings = session.service?.monitor ?? configuration?.monitor;
  const savedConfiguration = session.service ?? configuration;
  const config = run?.counting ?? savedConfiguration?.config;
  const zones = config?.zones ?? [];
  const classes = config?.classes ?? defaultCountingClasses;
  const live = source.kind === "stream";
  const currentData = Boolean(
    run?.counts?.valid &&
    (!active || (!session.stale && !session.error)) &&
    (!live || session.running),
  );
  const counts = currentData ? run!.counts : null;
  const totals = regionTotals(
    counts,
    classes,
    zones.map((item) => item.id),
  );
  const modelId = run?.model_id ?? settings?.model_id;
  const model = models.find((item) => item.id === modelId);
  const startModel = models.find((item) => item.id === settings?.model_id);
  const configured = Boolean(
    settings &&
    savedConfiguration?.config?.zones.length &&
    !savedConfiguration.stale &&
    startModel,
  );
  const servicePhase = session.service?.runtime?.phase;
  const statusLabel =
    session.service?.enabled && servicePhase === "blocked"
      ? "Cần kiểm tra cấu hình"
      : session.service?.enabled && servicePhase === "retrying"
        ? "Đang kết nối lại"
        : session.service?.enabled && !session.running
          ? "Đang nối lượt"
          : !session.ready || loading
            ? "Đang tải"
            : active
              ? run?.status === "queued"
                ? "Đang chờ AI"
                : !run?.result
                  ? "Đang chờ kết quả AI"
                  : session.stale || session.error
                    ? "Chưa có dữ liệu mới"
                    : "Đang giám sát"
              : run?.status === "failed"
                ? "Chạy thất bại"
                : run?.status === "completed"
                  ? live
                    ? "Đã hết thời lượng lượt"
                    : "Đã hoàn tất video"
                  : run?.status === "cancelled"
                    ? "Đã dừng"
                    : configured
                      ? "Sẵn sàng"
                      : "Cần cấu hình";
  async function start() {
    if (!configured || !settings || !configuration?.config) return;
    await session.start(() => startCountingProfile(profile.id));
  }
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-xl border bg-muted/40">
            <CameraIcon className="size-5 text-primary" />
          </span>
          <div className="min-w-0">
            <h2 className="truncate text-lg font-semibold">{profile.name}</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              {source.name} · {zones.length} vùng
              {settings?.continuous ? " · Liên tục" : ""}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span
            role="status"
            className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium ${active && currentData ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400" : "bg-muted text-muted-foreground"}`}
          >
            <span
              className={`size-1.5 rounded-full ${active && currentData ? "bg-emerald-500" : "bg-muted-foreground"}`}
            />
            {statusLabel}
          </span>
          {active ? (
            <Button
              variant="outline"
              disabled={session.busy}
              onClick={() => void session.stop()}
            >
              <SquareIcon />
              {session.busy ? "Đang dừng…" : "Dừng AI"}
            </Button>
          ) : (
            <Button
              disabled={!configured || !session.ready || session.busy}
              onClick={() => void start()}
            >
              <PlayIcon />
              {session.busy
                ? "Đang bắt đầu…"
                : run
                  ? "Chạy lại"
                  : "Bắt đầu giám sát"}
            </Button>
          )}
        </div>
      </div>
      {(configError || session.error || run?.error || run?.counts?.reason) && (
        <div
          role="alert"
          className="space-y-3 rounded-lg border border-destructive/30 p-4 text-sm text-destructive"
        >
          <p>
            {configError || session.error || run?.error || run?.counts?.reason}
          </p>
          {configError && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setRevision((value) => value + 1)}
            >
              Tải lại cấu hình
            </Button>
          )}
        </div>
      )}
      {!loading && !configured && !active && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-muted/30 p-4">
          <p className="text-sm text-muted-foreground">
            {configuration?.stale
              ? "Nguồn đã thay đổi. Cần vẽ lại vùng trước khi chạy."
              : !configuration?.config?.zones.length
                ? "Cấu hình chưa có vùng đếm."
                : !settings
                  ? "Chọn model và lưu thông số trước khi chạy."
                  : "Model không còn khả dụng. Chọn lại model."}
          </p>
          <Button variant="outline" size="sm" asChild>
            <Link href="/counting/configure">
              Thiết lập
              <ArrowRightIcon />
            </Link>
          </Button>
        </div>
      )}
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.8fr)_minmax(15rem,1fr)]">
        <WorkspaceSection
          title="Quan sát"
          titleId="monitor-preview-heading"
          actions={
            <span className="text-xs text-muted-foreground">
              {live
                ? connected
                  ? "Preview đang phát"
                  : "Chờ hình camera"
                : source.fps
                  ? `${source.fps} FPS nguồn`
                  : "Video file"}
            </span>
          }
        >
          <div className="space-y-4">
            <CountingPreview
              source={source}
              run={run}
              zones={zones}
              selected={null}
              draft={null}
              editable={false}
              boxes={preferences.boxes}
              labels={preferences.labels}
              segments={preferences.segments && model?.task === "segment"}
              anchors={anchors}
              showZones={showZones}
              onSelect={noop}
              onPoint={noop}
              onMove={noop}
              onDimensions={noop}
              onConnection={setConnected}
            />
            <p role="status" className="text-xs text-muted-foreground">
              {counts
                ? `${active ? "Mới nhất" : "Frame cuối"} · ${((counts.timestamp_ms ?? 0) / 1000).toFixed(2)}s`
                : "Chưa có dữ liệu"}
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <caption className="sr-only">
                  Số lượng từ kết quả AI theo từng vùng
                </caption>
                <thead>
                  <tr className="border-b text-muted-foreground">
                    <th className="py-3 text-left font-medium">Vùng</th>
                    {classes.map((key) => (
                      <th
                        key={key}
                        className="px-2 py-3 text-right font-medium whitespace-nowrap"
                      >
                        {countingClassLabel(key)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {zones.map((item) => {
                    const row = counts?.regions.find(
                      (row) => row.id === item.id,
                    );
                    return (
                      <tr key={item.id} className="border-b last:border-0">
                        <th className="py-3 text-left font-medium whitespace-nowrap">
                          <span
                            className="mr-2 inline-block size-2 rounded-full"
                            style={{ background: item.color }}
                          />
                          {item.name}
                        </th>
                        {classes.map((key) => (
                          <td
                            key={key}
                            className="px-2 py-3 text-right tabular-nums"
                          >
                            {item.classes.includes(key)
                              ? (row?.counts[key] ?? "—")
                              : "—"}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot className="border-t bg-muted/40 font-semibold">
                  <tr>
                    <th
                      scope="row"
                      className="py-3 text-left whitespace-nowrap"
                    >
                      Tổng cộng ({zones.length} vùng)
                    </th>
                    {classes.map((key, index) => (
                      <td
                        key={key}
                        className="px-2 py-3 text-right tabular-nums"
                      >
                        {totals[index] ?? "—"}
                      </td>
                    ))}
                  </tr>
                </tfoot>
              </table>
            </div>
            {!zones.length && (
              <p className="text-sm text-muted-foreground">Chưa có vùng đếm.</p>
            )}
            <p className="text-xs leading-5 text-muted-foreground">
              Đếm hiện diện, không cộng dồn. Vùng chồng nhau có thể đếm trùng.
            </p>
          </div>
        </WorkspaceSection>
        <div className="space-y-6">
          <section
            className="rounded-xl border p-4 md:p-6"
            aria-labelledby="service-health-heading"
          >
            <h2
              id="service-health-heading"
              className="flex items-center gap-2 text-sm font-semibold"
            >
              <HeartPulseIcon className="size-4 text-primary" />
              Vận hành
            </h2>
            <dl className="mt-5 divide-y text-xs">
              {[
                [
                  "Thời lượng lượt",
                  settings?.continuous
                    ? "Liên tục"
                    : live
                      ? `${(settings?.duration_seconds ?? 3600) / 60} phút`
                      : "Đến hết video",
                ],
                ["Chạy nền", "Tiếp tục khi đóng trình duyệt"],
                ["Tự khởi động", settings?.auto_start ? "Đã bật" : "Đã tắt"],
              ].map(([label, value]) => (
                <div
                  key={label}
                  className="flex items-start justify-between gap-3 py-3 first:pt-0 last:pb-0"
                >
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd className="text-right font-medium">{value}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-5 flex items-start gap-2 rounded-lg bg-muted p-3 text-xs leading-5 text-muted-foreground">
              <Clock3Icon className="mt-0.5 size-4 shrink-0" />
              {session.service?.runtime?.error ??
                (settings?.continuous
                  ? "Tự thử lại khi lỗi; nút Dừng tắt việc tự chạy lại."
                  : live
                    ? "Kết thúc khi hết thời lượng đã đặt."
                    : "Video chạy một lượt, không tự lặp.")}
            </p>
          </section>
          <section
            className="space-y-4 rounded-xl border p-4 md:p-6"
            aria-label="Tuỳ chọn hiển thị"
          >
            <OverlayControls
              preferences={preferences}
              onChange={update}
              pose={false}
              segment={model?.task === "segment"}
              canConnect={false}
              classify={false}
              independentLabels
              hideUnsupported
              extraControls={[
                {
                  id: "zones",
                  label: "Vùng đếm",
                  checked: showZones,
                  onChange: setShowZones,
                },
                {
                  id: "anchors",
                  label: "Điểm đếm",
                  checked: anchors,
                  onChange: setAnchors,
                },
              ]}
            />
          </section>
        </div>
      </div>
      <details className="rounded-xl border p-4 md:p-6">
        <summary className="cursor-pointer text-sm font-semibold">
          Hiệu năng và thông số
        </summary>
        <div className="mt-6 space-y-4">
          <RunMetrics
            result={run?.result ?? null}
            progress={run?.progress}
            video
          />
          <p className="break-words text-xs text-muted-foreground">
            Model: {run?.model_id ?? settings?.model_id ?? "—"} · Confidence{" "}
            {run?.options?.conf ?? settings?.options.conf ?? "—"} · IoU{" "}
            {run?.options?.iou ?? settings?.options.iou ?? "—"}
          </p>
          <p className="break-words text-xs text-muted-foreground">
            Class: {classes.join(", ")}
          </p>
        </div>
      </details>
    </>
  );
}
