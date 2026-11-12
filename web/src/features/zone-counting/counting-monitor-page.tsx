"use client";

import { supportsCounting } from "./counting-model";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import {
  ArrowRightIcon,
  CameraIcon,
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
  const [controlsTarget, setControlsTarget] = useState<HTMLDivElement | null>(
    null,
  );
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
        setModels(library.filter(supportsCounting));
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
    <WorkspacePage title="Counting Monitor" hideHeading>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-4">
        <div className="w-full space-y-2 sm:w-72">
          <Label htmlFor="monitor-profile" className="sr-only">
            Cấu hình giám sát
          </Label>
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
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <div
            ref={setControlsTarget}
            className="flex flex-wrap items-center gap-2"
          />
          <Button
            variant="outline"
            size="icon"
            aria-label="Làm mới cấu hình"
            title="Làm mới cấu hình"
            disabled={loading}
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
          controlsTarget={controlsTarget}
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
  controlsTarget,
}: {
  controlsTarget: HTMLDivElement | null;
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
      savedConfiguration?.config &&
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
  const controls = (
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
  );
  return (
    <>
      {controlsTarget ? createPortal(controls, controlsTarget) : controls}
      {(configError ||
        session.error ||
        run?.error ||
        run?.counts?.reason ||
        session.service?.runtime?.error) && (
        <div
          role="alert"
          className="space-y-3 rounded-lg border border-destructive/30 p-4 text-sm text-destructive"
        >
          <p>
            {configError ||
              session.error ||
              run?.error ||
              run?.counts?.reason ||
              session.service?.runtime?.error}
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
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_17rem]">
        <section
          aria-labelledby="monitor-preview-heading"
          className="min-w-0 space-y-3"
        >
          <div className="flex min-w-0 items-center justify-between gap-3">
            <h2
              id="monitor-preview-heading"
              className="truncate text-sm font-semibold"
              title={source.name}
            >
              {source.name}
            </h2>
            <span className="shrink-0 text-xs text-muted-foreground">
              {live ? (connected ? "Camera đang phát" : "Chờ camera") : "Video"}
            </span>
          </div>
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
            showIdleHint={false}
            onSelect={noop}
            onPoint={noop}
            onMove={noop}
            onDimensions={noop}
            onConnection={setConnected}
          />
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="rounded-md bg-muted px-2 py-1">
              {settings?.continuous
                ? "24/7"
                : live
                  ? `${(settings?.duration_seconds ?? 3600) / 60} phút`
                  : "Một lượt"}
            </span>
            <span>
              {zones.length} vùng · {classes.length} class
            </span>
            {settings?.continuous && (
              <span>· Tự khởi động {settings.auto_start ? "bật" : "tắt"}</span>
            )}
          </div>
        </section>
        <aside
          className="min-w-0 space-y-5 rounded-xl border p-4"
          aria-label="Hiển thị và thông số"
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
          <dl className="space-y-3 border-t pt-4 text-xs">
            {[
              ["Model", model?.name ?? model?.filename ?? modelId ?? "—"],
              [
                "Confidence / IoU",
                `${run?.options?.conf ?? settings?.options.conf ?? "—"} / ${run?.options?.iou ?? settings?.options.iou ?? "—"}`,
              ],
              [
                "Thiết bị",
                run?.result?.device ??
                  (settings?.options.device === "auto"
                    ? "Tự động"
                    : (settings?.options.device ?? "—")),
              ],
            ].map(([label, value]) => (
              <div
                key={label}
                className="flex min-w-0 items-start justify-between gap-3"
              >
                <dt className="shrink-0 text-muted-foreground">{label}</dt>
                <dd className="min-w-0 break-all text-right font-medium">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
          <section
            className="space-y-3 border-t pt-4"
            aria-label="Hiệu năng AI"
          >
            <h3 className="text-sm font-semibold">Hiệu năng AI</h3>
            <RunMetrics
              result={run?.result ?? null}
              progress={run?.progress}
              video
              compact
            />
          </section>
        </aside>
      </div>
      <WorkspaceSection
        title="Số đếm theo vùng"
        titleId="monitor-counts-heading"
        variant="plain"
        toolbarLabel="Kết quả đếm"
        toolbar={
          <div className="flex w-full flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-semibold">Số đếm theo vùng</span>
            <span role="status" className="text-xs text-muted-foreground">
              {counts
                ? `${active ? "Mới nhất" : "Frame cuối"} · ${((counts.timestamp_ms ?? 0) / 1000).toFixed(2)}s`
                : zones.length
                  ? "Chưa có dữ liệu"
                  : "Không đếm"}
            </span>
          </div>
        }
      >
        {zones.length > 0 && (
          <div
            className="overflow-x-auto rounded-xl border"
            role="region"
            aria-label="Số đếm theo vùng"
            tabIndex={0}
          >
            <table className="w-full text-sm">
              <caption className="sr-only">
                Số lượng từ kết quả AI theo từng vùng
              </caption>
              <thead>
                <tr className="border-b text-muted-foreground">
                  <th className="px-4 py-3 text-left font-medium">Vùng</th>
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
                  const row = counts?.regions.find((row) => row.id === item.id);
                  return (
                    <tr key={item.id} className="border-b last:border-0">
                      <th className="px-4 py-3 text-left font-medium whitespace-nowrap">
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
                    className="px-4 py-3 text-left whitespace-nowrap"
                  >
                    Tổng cộng ({zones.length} vùng)
                  </th>
                  {classes.map((key, index) => (
                    <td key={key} className="px-2 py-3 text-right tabular-nums">
                      {totals[index] ?? "—"}
                    </td>
                  ))}
                </tr>
              </tfoot>
            </table>
          </div>
        )}
        {!zones.length && (
          <p className="mt-3 text-sm text-muted-foreground">
            Chưa có vùng · chỉ nhận diện, không đếm.
          </p>
        )}
        {zones.length > 0 && (
          <p className="mt-3 text-xs text-muted-foreground">
            Đếm theo từng frame; vùng chồng nhau tính riêng.
          </p>
        )}
      </WorkspaceSection>
    </>
  );
}
