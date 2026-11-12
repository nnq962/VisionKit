"use client";

import { createUuid } from "@/lib/uuid";

import {
  useCallback,
  useEffect,
  useImperativeHandle,
  useState,
  type Ref,
} from "react";
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  PlayIcon,
  DownloadIcon,
  CheckIcon,
  SquareIcon,
  PlusIcon,
  SaveIcon,
  RotateCcwIcon,
} from "lucide-react";
import { toast } from "sonner";
import { WorkspaceSection } from "@/components/workspace-page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { VisionSource } from "@/features/sources/types";
import type { StoredModel } from "@/features/models/api";
import { OverlayControls } from "@/features/inference/components/overlay-controls";
import { RunMetrics } from "@/features/inference/components/run-metrics";
import { ThresholdSlider } from "@/features/pipelines/yolo/components/parameters/threshold-slider";
import { CountingPreview } from "./counting-preview";
import { CountingSchedule } from "./counting-schedule";
import { CountingClassPicker } from "./counting-class-picker";
import {
  countingModelClasses,
  reconcileCountingClasses,
  usesCountingPrompts,
} from "./counting-model";
import {
  defaultCountingClasses,
  countingClassLabel,
  type CountingProfile,
  type CountingZone,
  type Point,
} from "./types";
import {
  parseTextPrompts,
  validateTextPrompts,
} from "@/features/pipelines/yolo/text-prompts";
import {
  getCountingConfig,
  saveCountingConfig,
  saveCountingProfile,
  startCountingRun,
} from "./api";
import { polygonError } from "./geometry";
import { useCountingRun } from "./use-counting-run";

const colors = ["#22d3ee", "#a3e635", "#fbbf24", "#fb7185", "#c4b5fd"];

export type CountingEditorHandle = { save: () => Promise<boolean> };

export function ZoneWorkspace({
  ref,
  source,
  model,
  onLock,
  onRestoreModel,
  step,
  onStepChange,
  onRestoreRun,
  configureOnly = false,
  profileId,
  profileName,
  initialProfile,
  onProfileSaved,
  onDirtyChange,
}: {
  ref?: Ref<CountingEditorHandle>;
  configureOnly?: boolean;
  profileId?: string | null;
  profileName?: string;
  initialProfile?: CountingProfile | null;
  onProfileSaved?: (profile: CountingProfile) => void;
  onDirtyChange?: (dirty: boolean) => void;
  step: number;
  onStepChange: (step: number) => void;
  onRestoreRun: () => void;
  source: VisionSource;
  model: StoredModel | null;
  onLock: (locked: boolean) => void;
  onRestoreModel: (id: string) => void;
}) {
  const session = useCountingRun(source.id);
  const { run, active } = session;
  const [classModelId, setClassModelId] = useState<string | null>(null);
  const promptMode = usesCountingPrompts(model);
  const availableClasses = countingModelClasses(model);
  const [classes, setClasses] = useState<string[]>(defaultCountingClasses);
  const [classText, setClassText] = useState(defaultCountingClasses.join("\n"));
  const classTextChanged =
    promptMode &&
    JSON.stringify(parseTextPrompts(classText)) !== JSON.stringify(classes);
  const [zones, setZones] = useState<CountingZone[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState<Point[] | null>(null);
  const [dimensions, setDimensions] = useState({
    width: source.width ?? 0,
    height: source.height ?? 0,
  });
  const [reference, setReference] = useState<{
    width: number;
    height: number;
  } | null>(null);
  const [signature, setSignature] = useState("");
  const [saved, setSaved] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [conf, setConf] = useState("0.25");
  const [iou, setIou] = useState("0.7");
  const [fps, setFps] = useState("5");
  const [minutes, setMinutes] = useState("60");
  const [continuous, setContinuous] = useState(false);
  const [autoStart, setAutoStart] = useState(false);
  const [savedEditor, setSavedEditor] = useState<string | null>(null);
  const [device, setDevice] = useState("auto");
  const [labels, setLabels] = useState(true);
  const [boxes, setBoxes] = useState(true);
  const [segments, setSegments] = useState(false);
  const [anchors, setAnchors] = useState(true);
  const [connected, setConnected] = useState(source.kind !== "stream");
  const canEditRun = configureOnly ? !active : !run;
  const editable =
    (step === 2 || (configureOnly && step === 3)) &&
    canEditRun &&
    !loading &&
    !saving &&
    !session.busy &&
    session.ready;
  const locked =
    (!configureOnly && Boolean(run)) ||
    session.busy ||
    saving ||
    loading ||
    !session.ready;
  const restoredModel = run?.model_id;
  const original = reference ?? dimensions;
  const config = {
    version: 1 as const,
    classes,
    reference_width: original.width || 1,
    reference_height: original.height || 1,
    zones,
  };
  const changed = JSON.stringify(config) !== saved;
  const editorFingerprint = JSON.stringify({
    config,
    classText,
    draft,
    conf,
    iou,
    fps,
    minutes,
    device,
    continuous,
    autoStart,
  });
  useEffect(() => {
    onDirtyChange?.(
      !loading && savedEditor !== null && editorFingerprint !== savedEditor,
    );
  }, [loading, savedEditor, editorFingerprint, onDirtyChange]);
  const aspectChanged = Boolean(
    zones.length &&
      dimensions.width &&
      reference &&
      Math.abs(
        dimensions.width /
          dimensions.height /
          (reference.width / reference.height) -
          1,
      ) > 0.01,
  );
  const zone = zones.find((item) => item.id === selected);
  useEffect(() => {
    onLock(locked);
    return () => onLock(false);
  }, [locked, onLock]);
  useEffect(() => {
    if (restoredModel && !configureOnly) {
      onRestoreModel(restoredModel);
      onRestoreRun();
    }
  }, [restoredModel, onRestoreModel, onRestoreRun, configureOnly, active]);
  useEffect(() => {
    const controller = new AbortController();
    void getCountingConfig(source.id, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        setSignature(value.source_signature);
        // Cấu hình mới không nhận vùng/thông số từ cấu hình khác cùng nguồn.
        const selectedProfile =
          initialProfile?.source_id === source.id ? initialProfile : null;
        const stored = configureOnly ? selectedProfile : value;
        const restored = stored?.stale ? null : stored?.config;
        const monitor = stored?.monitor;
        if (monitor) {
          setContinuous(Boolean(monitor.continuous));
          setAutoStart(Boolean(monitor.auto_start));
          setConf(String(monitor.options.conf));
          setIou(String(monitor.options.iou));
          setFps(String(monitor.options.max_fps));
          setDevice(monitor.options.device);
          setMinutes(String(monitor.duration_seconds / 60));
          if (configureOnly) onRestoreModel(monitor.model_id);
        }
        setClassModelId(monitor?.model_id ?? null);
        const restoredClasses = restored?.classes ?? defaultCountingClasses;
        setSavedEditor(
          JSON.stringify({
            config: {
              version: 1,
              classes: restoredClasses,
              reference_width: restored?.reference_width ?? source.width ?? 0,
              reference_height:
                restored?.reference_height ?? source.height ?? 0,
              zones: restored?.zones ?? [],
            },
            classText: restoredClasses.join("\n"),
            draft: null,
            conf: String(monitor?.options.conf ?? 0.25),
            iou: String(monitor?.options.iou ?? 0.7),
            fps: String(monitor?.options.max_fps ?? 5),
            minutes: String((monitor?.duration_seconds ?? 3600) / 60),
            device: monitor?.options.device ?? "auto",
            continuous: Boolean(monitor?.continuous),
            autoStart: Boolean(monitor?.auto_start),
          }),
        );
        setClasses(restoredClasses);
        setClassText(restoredClasses.join("\n"));
        setZones(restored?.zones ?? []);
        setSelected(restored?.zones[0]?.id ?? null);
        if (restored) {
          setReference({
            width: restored.reference_width,
            height: restored.reference_height,
          });
          setSaved(JSON.stringify({ ...restored, classes: restoredClasses }));
        }
        if (stored?.stale)
          setNotice(
            "Nguồn đã thay đổi. Vẽ và lưu lại vùng cho nguồn hiện tại.",
          );
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError((reason as Error).message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [
    source.id,
    source.width,
    source.height,
    configureOnly,
    onRestoreModel,
    initialProfile,
  ]);
  if (!loading && model && classModelId !== model.id) {
    setClassModelId(model.id);
    if (!usesCountingPrompts(model)) {
      const next = countingModelClasses(model);
      setClasses(next);
      setClassText(next.join("\n"));
      setZones((items) =>
        items.map((item) => ({
          ...item,
          classes: reconcileCountingClasses(item.classes, next),
        })),
      );
      setDraft(null);
      setError("");
    }
  }
  const onDimensions = useCallback(
    (width: number, height: number) => setDimensions({ width, height }),
    [],
  );
  const patchZone = (patch: Partial<CountingZone>) => {
    setZones((items) =>
      items.map((item) =>
        item.id === selected ? { ...item, ...patch } : item,
      ),
    );
    setNotice("");
  };
  function finishDraft() {
    if (!draft) return;
    const message = polygonError(draft);
    if (message) {
      setError(message);
      return;
    }
    const next: CountingZone = {
      id: createUuid(),
      name: `Vùng ${zones.length + 1}`,
      color: colors[zones.length % colors.length],
      points: draft,
      classes: [...classes],
    };
    setZones([...zones, next]);
    setSelected(next.id);
    setDraft(null);
    setError("");
    setNotice("");
    if (!reference || !zones.length) setReference(dimensions);
  }
  function applyClasses() {
    const invalid = validateTextPrompts(classText);
    if (invalid) {
      setError(invalid);
      return;
    }
    const next = parseTextPrompts(classText);
    updateClasses(next);
    setNotice("Đã áp dụng class.");
  }
  function updateClasses(next: string[]) {
    setZones((items) =>
      items.map((item) => {
        const kept = item.classes.filter((label) => next.includes(label));
        const allSelected = classes.every((label) =>
          item.classes.includes(label),
        );
        return {
          ...item,
          classes: allSelected || !kept.length ? [...next] : kept,
        };
      }),
    );
    setClasses(next);
    setClassText(next.join("\n"));
    setError("");
    setNotice("");
  }
  function validate() {
    if (!classes.length) return "Chọn ít nhất một class cần đếm.";
    if (!promptMode && classes.some((name) => !availableClasses.includes(name)))
      return "Chọn lại class từ nhãn có sẵn của model hiện tại.";
    if (classTextChanged)
      return "Bấm Áp dụng class trước khi lưu hoặc tiếp tục.";
    if (!signature)
      return "Chưa tải được cấu hình nguồn. Tải lại trang để thử lại.";
    if (zones.length && (!original.width || !original.height))
      return "Chờ video hoặc camera có hình trước khi vẽ vùng.";
    if (aspectChanged)
      return "Tỷ lệ khung hình đã đổi. Xoá các vùng cũ và vẽ lại.";
    if (draft !== null) return "Hoàn tất hoặc huỷ nét vẽ trước.";
    for (const region of zones) {
      const invalid = polygonError(region.points);
      if (invalid) return `${region.name}: ${invalid}`;
      if (!region.name.trim() || !region.classes.length)
        return "Mỗi vùng cần có tên và ít nhất một class.";
    }
    return "";
  }
  async function save() {
    if (loading || saving || !session.ready || session.busy) return false;
    const invalid =
      validate() ||
      (configureOnly && !profileName?.trim()
        ? "Nhập tên cấu hình trước khi lưu."
        : "");
    if (invalid) {
      setError(invalid);
      toast.error(invalid);
      return false;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      if (configureOnly && (!model || validateParameters())) {
        const message = !model
          ? "Chọn model YOLO / YOLOE trước khi lưu."
          : validateParameters();
        setError(message);
        toast.error(message);
        return false;
      }
      if (configureOnly && model) {
        const result = await saveCountingProfile(profileId ?? null, {
          name: profileName?.trim() ?? "",
          source_id: source.id,
          source_signature: signature,
          config,
          monitor: {
            model_id: model.id,
            options: {
              conf: Number(conf),
              iou: Number(iou),
              device,
              max_fps: Number(fps),
            },
            duration_seconds: continuous ? 3600 : Number(minutes) * 60,
            continuous,
            auto_start: continuous && autoStart,
          },
        });
        setSaved(JSON.stringify(result.config));
        setSavedEditor(editorFingerprint);
        setNotice("");
        toast.success(`Đã lưu “${result.name}”.`);
        onProfileSaved?.(result);
      } else {
        const result = await saveCountingConfig(source.id, signature, config);
        setSaved(JSON.stringify(result.config));
        setNotice("Đã lưu vùng theo nguồn.");
      }
      return true;
    } catch (reason) {
      setError((reason as Error).message);
      toast.error((reason as Error).message);
      return false;
    } finally {
      setSaving(false);
    }
  }
  function validateParameters() {
    if (
      ![conf, iou].every(
        (value) =>
          value.trim() &&
          Number.isFinite(Number(value)) &&
          Number(value) >= 0 &&
          Number(value) <= 1,
      ) ||
      !Number.isFinite(Number(fps)) ||
      Number(fps) < 1 ||
      Number(fps) > 60 ||
      (!(configureOnly && continuous) &&
        (!Number.isInteger(Number(minutes)) ||
          Number(minutes) < 1 ||
          Number(minutes) > 240))
    ) {
      return "Confidence/IoU phải từ 0–1, FPS từ 1–60 và thời lượng từ 1–240 phút.";
    }
    return "";
  }
  async function next() {
    const invalid = validate() || validateParameters();
    if (invalid) {
      setError(invalid);
      return;
    }
    if ((changed || configureOnly) && !(await save())) return;
    setError("");
    if (!configureOnly) {
      setNotice("");
      onStepChange(3);
    }
  }
  async function start() {
    const invalid = validate();
    if (invalid || !model) {
      setError(invalid || "Chọn model YOLO / YOLOE trước.");
      return;
    }
    const invalidParameters = validateParameters();
    if (invalidParameters) {
      setError(invalidParameters);
      return;
    }
    if (changed && !(await save())) return;
    setError("");
    setNotice("");
    await session.start(() =>
      startCountingRun(
        source.id,
        model.id,
        signature,
        config,
        { conf: Number(conf), iou: Number(iou), device, max_fps: Number(fps) },
        Number(minutes),
      ),
    );
  }
  const displayedZones = configureOnly
    ? zones
    : (run?.counting?.zones ?? zones);
  const displayedClasses = configureOnly
    ? classes
    : (run?.counting?.classes ?? (run ? defaultCountingClasses : classes));
  const unavailable =
    !run?.counts?.valid ||
    (active && Boolean(session.error)) ||
    (source.kind === "stream" && (session.stale || run.status === "failed"));
  const counts = unavailable ? null : run?.counts;
  const message =
    configureOnly && !active
      ? "Chỉnh vùng và lưu cấu hình."
      : active
        ? unavailable
          ? "Đang chờ dữ liệu AI mới…"
          : "Đang đếm hiện diện"
        : run
          ? {
              completed: "Đã hoàn tất · kết quả frame cuối",
              cancelled: "Đã dừng · kết quả frame cuối",
              failed: "Lượt đếm bị gián đoạn",
              queued: "Đang chờ",
              running: "Đang đếm",
            }[run.status]
          : step === 2
            ? "Sẵn sàng thiết lập vùng"
            : "Sẵn sàng bắt đầu đếm";
  useImperativeHandle(ref, () => ({ save }));
  const displayControls = (
    <>
      <OverlayControls
        preferences={{
          boxes,
          labels,
          segments,
          keypoints: false,
          skeleton: false,
        }}
        onChange={(next) => {
          setBoxes(next.boxes);
          setLabels(next.labels);
          setSegments(next.segments);
        }}
        pose={false}
        segment={model?.task === "segment"}
        canConnect={false}
        classify={false}
        independentLabels
        hideUnsupported
        extraControls={[
          {
            id: "anchors",
            label: "Điểm đếm",
            checked: anchors,
            onChange: setAnchors,
          },
        ]}
      />
    </>
  );
  const runActions = (
    <>
      {active ? (
        <Button
          variant="outline"
          disabled={session.busy}
          onClick={() => void session.stop()}
        >
          <SquareIcon />
          Dừng đếm
        </Button>
      ) : run ? (
        <Button
          variant="outline"
          disabled={session.busy}
          onClick={async () => {
            if (await session.reset()) {
              if (run.options) {
                setConf(String(run.options.conf));
                setIou(String(run.options.iou));
                setDevice(run.options.device);
                setFps(String(run.options.max_fps));
              }
              onStepChange(2);
            }
          }}
        >
          <RotateCcwIcon />
          Thiết lập lại
        </Button>
      ) : (
        <Button
          disabled={
            loading ||
            !session.ready ||
            saving ||
            session.busy ||
            !model ||
            draft !== null ||
            aspectChanged
          }
          onClick={() => void start()}
        >
          <PlayIcon />
          {session.busy ? "Đang bắt đầu…" : "Bắt đầu đếm"}
        </Button>
      )}
      {run && !active && (
        <Button
          variant="outline"
          disabled={session.busy || !model}
          onClick={async () => {
            if (await session.reset())
              await session.start(() =>
                startCountingRun(
                  source.id,
                  run.model_id,
                  signature,
                  run.counting,
                  run.options,
                  Number(minutes),
                ),
              );
          }}
        >
          <PlayIcon /> Chạy lại
        </Button>
      )}
      {run && !active && (
        <Button
          variant="outline"
          disabled={session.busy}
          onClick={async () => {
            if (await session.reset()) onStepChange(0);
          }}
        >
          <CheckIcon /> Hoàn thành
        </Button>
      )}
      {run?.result && (
        <Button
          variant="outline"
          onClick={() => {
            const url = URL.createObjectURL(
              new Blob([JSON.stringify(run, null, 2)], {
                type: "application/json",
              }),
            );
            const link = document.createElement("a");
            link.href = url;
            link.download = `visionkit-counting-${run.id}.json`;
            link.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          }}
        >
          <DownloadIcon /> JSON frame cuối
        </Button>
      )}
    </>
  );
  const classEditor = (
    <fieldset disabled={!editable || draft !== null} className="space-y-4">
      <legend
        className={configureOnly ? "sr-only" : "mb-4 text-sm font-semibold"}
      >
        Đối tượng cần đếm
      </legend>
      {promptMode ? (
        <>
          <div className="space-y-2">
            <Label htmlFor="counting-classes">Text prompt YOLOE</Label>
            <textarea
              id="counting-classes"
              className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] disabled:opacity-50"
              value={classText}
              rows={5}
              onChange={(event) => {
                setClassText(event.target.value);
                setError("");
              }}
              aria-describedby="counting-classes-hint"
              placeholder={"person\ncar\nlaptop\ncell phone"}
            />
            <p
              id="counting-classes-hint"
              className="text-xs leading-5 text-muted-foreground"
            >
              Tên tiếng Anh · mỗi dòng một class · tối đa 80.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              disabled={!classTextChanged}
              onClick={applyClasses}
            >
              Áp dụng class
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                setClassText(defaultCountingClasses.join("\n"));
                setError("");
              }}
            >
              Bộ class y tế
            </Button>
          </div>
        </>
      ) : (
        <CountingClassPicker
          names={availableClasses}
          selected={classes}
          onChange={updateClasses}
        />
      )}
    </fieldset>
  );
  const parameterEditor = (
    <fieldset
      disabled={!editable}
      className={configureOnly ? "space-y-5" : "grid gap-6 sm:grid-cols-2"}
    >
      <legend className="mb-4 text-sm font-semibold">Thông số nhận diện</legend>
      <ThresholdSlider
        id="count-confidence"
        label="Confidence"
        hint="Ngưỡng tin cậy · 0–1."
        value={conf}
        onChange={setConf}
      />
      <ThresholdSlider
        id="count-iou"
        label="IoU / NMS"
        hint="Ngưỡng lọc bbox trùng · 0–1."
        value={iou}
        onChange={setIou}
      />
      <div className="space-y-2">
        <Label htmlFor="count-device" className="flex h-8 items-center">
          Thiết bị
        </Label>
        <Select value={device} onValueChange={setDevice}>
          <SelectTrigger id="count-device" className="h-8 w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectItem value="auto">Tự động</SelectItem>
              <SelectItem value="cpu">CPU</SelectItem>
              <SelectItem value="cuda:0">CUDA:0</SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
      </div>
      {!configureOnly && source.kind === "stream" && (
        <>
          <div className="space-y-2">
            <Label htmlFor="count-fps" className="flex h-8 items-center">
              Giới hạn AI (FPS)
            </Label>
            <Input
              id="count-fps"
              className="h-8"
              type="number"
              min="1"
              max="60"
              value={fps}
              onChange={(e) => setFps(e.target.value)}
            />
          </div>
          {!continuous && (
            <div className="space-y-2">
              <Label htmlFor="count-minutes" className="flex h-8 items-center">
                Thời lượng (phút)
              </Label>
              <Input
                id="count-minutes"
                className="h-8"
                type="number"
                min="1"
                max="240"
                value={minutes}
                onChange={(e) => setMinutes(e.target.value)}
              />
            </div>
          )}
        </>
      )}
    </fieldset>
  );
  const regionEditor = (
    <div
      className={
        step === 2
          ? "grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]"
          : "grid items-start gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]"
      }
    >
      <div className="min-w-0 space-y-3 lg:sticky lg:top-6">
        {canEditRun && (
          <div className="flex flex-wrap gap-2">
            {draft === null ? (
              <Button
                variant="outline"
                size="sm"
                disabled={!editable || !dimensions.width || zones.length >= 20}
                onClick={() => {
                  setDraft([]);
                  setSelected(null);
                  setError("");
                }}
              >
                <PlusIcon />
                Vẽ vùng
              </Button>
            ) : (
              <>
                <Button
                  type="button"
                  size="sm"
                  disabled={draft.length < 3}
                  onClick={finishDraft}
                >
                  Hoàn tất vùng
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setDraft((items) => items?.slice(0, -1) ?? null)
                  }
                >
                  Bỏ đỉnh cuối
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setDraft(null);
                    setError("");
                  }}
                >
                  Huỷ nét vẽ
                </Button>
                <span className="self-center text-xs text-muted-foreground">
                  {draft.length} đỉnh
                </span>
              </>
            )}
            {!configureOnly && (
              <Button
                variant="outline"
                size="sm"
                disabled={!editable || draft !== null || !changed}
                onClick={() => void save()}
              >
                <SaveIcon />
                {saving ? "Đang lưu…" : "Lưu vùng"}
              </Button>
            )}
          </div>
        )}
        {draft !== null && error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <CountingPreview
          key={source.id}
          source={source}
          run={configureOnly ? null : run}
          zones={displayedZones}
          selected={selected}
          draft={draft}
          editable={(editable && step === 2) || (step === 2 && saving)}
          interactionDisabled={saving}
          boxes={boxes}
          labels={labels}
          segments={segments}
          anchors={anchors}
          onSelect={setSelected}
          onDimensions={onDimensions}
          onConnection={setConnected}
          onPoint={(point) => {
            if (draft && draft.length >= 32) {
              setError("Tối đa 32 đỉnh mỗi vùng.");
              return;
            }
            setDraft((items) => (items ? [...items, point] : items));
          }}
          onMove={(id, index, point) =>
            setZones((items) =>
              items.map((item) =>
                item.id === id
                  ? {
                      ...item,
                      points: item.points.map((p, i) =>
                        i === index ? point : p,
                      ),
                    }
                  : item,
              ),
            )
          }
        />
        {step === 2 && (
          <div className="rounded-lg border px-4 py-3">{displayControls}</div>
        )}
        <p className="text-xs leading-5 text-muted-foreground">
          Đếm điểm giữa đáy khung theo từng frame, riêng cho mỗi vùng.
        </p>
      </div>
      {!configureOnly && step === 3 && (
        <aside
          aria-label="Tuỳ chọn hiển thị"
          className="min-w-0 space-y-4 border-t pt-6 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-6"
        >
          {displayControls}
          {run?.result && (
            <p className="border-t pt-4 text-xs text-muted-foreground">
              Frame {run.result.frameId ?? 0} ·{" "}
              {((run.result.timestampMs ?? 0) / 1000).toFixed(2)}s
            </p>
          )}
        </aside>
      )}
      <div
        hidden={step !== 2}
        className="min-w-0 space-y-4 rounded-xl border p-4"
      >
        {configureOnly && (
          <section
            className="space-y-3 border-b pb-4"
            aria-label="Đối tượng cần đếm"
          >
            <h3 className="text-sm font-semibold">
              Đối tượng cần đếm{" "}
              <span className="text-xs font-normal text-muted-foreground">
                {promptMode ? `(${classes.length})` : ""}
              </span>
            </h3>
            {classEditor}
          </section>
        )}
        <h3 className="text-sm font-semibold">
          Vùng đếm{" "}
          <span className="ml-1 text-xs font-normal text-muted-foreground">
            {zones.length} / 20
          </span>
        </h3>
        {draft !== null && (
          <p className="text-sm text-muted-foreground">
            Bấm thêm đỉnh ({draft.length}/32) → Hoàn tất vùng.
          </p>
        )}
        <div
          className="space-y-1 rounded-lg border p-1"
          aria-label="Danh sách vùng"
        >
          {displayedZones.length ? (
            displayedZones.map((item) => (
              <Button
                key={item.id}
                variant={selected === item.id ? "secondary" : "ghost"}
                className="w-full justify-start"
                onClick={() => setSelected(item.id)}
              >
                <span
                  className="size-3 shrink-0 rounded-full"
                  style={{ background: item.color }}
                />
                {item.name}
              </Button>
            ))
          ) : (
            <p className="p-3 text-xs leading-5 text-muted-foreground">
              Chưa có vùng · chỉ nhận diện, không đếm.
            </p>
          )}
        </div>
        {zone && editable && draft === null && (
          <div className="space-y-4 border-t pt-4">
            <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-3">
              <div className="space-y-2">
                <Label htmlFor="zone-name">Tên vùng</Label>
                <Input
                  id="zone-name"
                  value={zone.name}
                  maxLength={60}
                  onChange={(event) => patchZone({ name: event.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="zone-color">Màu vùng</Label>
                <input
                  id="zone-color"
                  className="h-9 w-12 cursor-pointer rounded-md border border-input bg-transparent p-1"
                  type="color"
                  value={zone.color}
                  onChange={(event) => patchZone({ color: event.target.value })}
                />
              </div>
            </div>
            <fieldset className="grid max-h-48 grid-cols-2 gap-2 overflow-y-auto">
              <legend className="mb-2 text-sm font-medium">
                Class trong vùng
              </legend>
              {classes.map((key) => (
                <label key={key} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="size-3.5 shrink-0 accent-primary"
                    checked={zone.classes.includes(key)}
                    onChange={(event) =>
                      patchZone({
                        classes: event.target.checked
                          ? [...zone.classes, key]
                          : zone.classes.filter((value) => value !== key),
                      })
                    }
                  />
                  {countingClassLabel(key)}
                </label>
              ))}
            </fieldset>
            <p className="text-xs text-muted-foreground">
              Kéo đỉnh để sửa vùng.
            </p>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => {
                setZones((items) =>
                  items.filter((item) => item.id !== selected),
                );
                setSelected(null);
                if (zones.length === 1) setReference(null);
              }}
            >
              Xoá vùng
            </Button>
          </div>
        )}
      </div>
    </div>
  );
  if (configureOnly)
    return (
      <WorkspaceSection
        title={step === 3 ? "Thông số & chế độ chạy" : "Thiết lập vùng đếm"}
        titleId="counting-configuration-heading"
        variant="plain"
        showHeader={false}
        toolbarLabel="Thao tác cấu hình đếm vùng"
        toolbar={
          <div className="flex w-full flex-wrap items-center justify-between gap-3">
            <div>
              <span className="text-sm font-semibold">
                {step === 3 ? "Thông số & chế độ chạy" : "Thiết lập vùng đếm"}
              </span>
              <p className="mt-1 text-xs text-muted-foreground">
                {step === 3
                  ? "Điều chỉnh nhận diện và chọn cách vận hành."
                  : "Vẽ vùng nếu cần đếm; bỏ qua để chỉ nhận diện."}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="ghost"
                disabled={locked}
                onClick={() => onStepChange(step === 3 ? 2 : 1)}
              >
                <ArrowLeftIcon />
                Quay lại
              </Button>
              {active && (
                <Button
                  variant="outline"
                  disabled={session.busy}
                  onClick={() => void session.stop()}
                >
                  <SquareIcon />
                  Dừng để chỉnh sửa
                </Button>
              )}
              <Button
                size="lg"
                disabled={
                  !editable ||
                  !model ||
                  draft !== null ||
                  aspectChanged ||
                  (step === 3 && !profileName?.trim())
                }
                onClick={() => {
                  if (step === 2) {
                    const invalid = validate();
                    if (invalid) {
                      setError(invalid);
                      return;
                    }
                    setError("");
                    onStepChange(3);
                  } else void save();
                }}
              >
                {step === 2 ? <ArrowRightIcon /> : <SaveIcon />}
                {step === 2
                  ? "Thông số & chế độ chạy"
                  : saving
                    ? "Đang lưu…"
                    : continuous && autoStart
                      ? "Lưu & chạy 24/7"
                      : "Lưu cấu hình"}
              </Button>
            </div>
          </div>
        }
      >
        {(error || session.error) && (
          <p
            role="alert"
            className="mb-4 rounded-lg bg-destructive/5 p-3 text-sm text-destructive"
          >
            {error || session.error}
          </p>
        )}
        {active && (
          <p role="status" className="mb-4 text-sm text-muted-foreground">
            Nguồn đang chạy. Dừng để chỉnh sửa cấu hình.
          </p>
        )}
        {notice && (
          <p role="status" className="mb-4 text-sm text-muted-foreground">
            {notice}
          </p>
        )}
        <div hidden={step !== 2}>{regionEditor}</div>
        <div hidden={step !== 3} className="space-y-6">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg bg-muted/40 px-4 py-3 text-xs text-muted-foreground">
            <span className="min-w-0 break-all">
              Nguồn:{" "}
              <strong className="font-medium text-foreground">
                {source.name}
              </strong>
            </span>
            <span>
              Model:{" "}
              <strong className="font-medium text-foreground">
                {model?.name ?? model?.filename}
              </strong>
            </span>
            <span>
              {zones.length} vùng · {classes.length} class
            </span>
            <Button
              size="sm"
              variant="ghost"
              disabled={locked}
              onClick={() => onStepChange(2)}
            >
              Sửa vùng
            </Button>
          </div>
          <div className="grid items-start gap-6 lg:grid-cols-2">
            <section
              aria-label="Thông số nhận diện"
              className="rounded-xl border p-4 md:p-6"
            >
              {parameterEditor}
            </section>
            <CountingSchedule
              disabled={!editable}
              sourceKind={source.kind}
              continuous={continuous}
              autoStart={autoStart}
              fps={fps}
              minutes={minutes}
              onFpsChange={setFps}
              onMinutesChange={setMinutes}
              onContinuousChange={(value) => {
                setContinuous(value);
                if (!value) setAutoStart(false);
              }}
              onAutoStartChange={setAutoStart}
            />
          </div>
        </div>
      </WorkspaceSection>
    );
  return (
    <>
      <WorkspaceSection
        title={step === 2 ? "Vùng và thông số" : "Chạy và kết quả"}
        titleId="counting-zones-heading"
        actions={
          <>
            <Button
              variant="outline"
              disabled={locked || loading}
              onClick={() => {
                setError("");
                onStepChange(step === 2 ? 1 : 2);
              }}
            >
              <ArrowLeftIcon /> Quay lại
            </Button>
            {step === 2 ? (
              <Button
                disabled={
                  loading ||
                  saving ||
                  session.busy ||
                  !session.ready ||
                  !model ||
                  draft !== null ||
                  (!configureOnly && !editable) ||
                  aspectChanged
                }
                onClick={() => void (configureOnly ? save() : next())}
              >
                {saving
                  ? "Đang lưu…"
                  : configureOnly
                    ? "Lưu cấu hình"
                    : "Tiếp tục"}{" "}
                {configureOnly ? <SaveIcon /> : <ArrowRightIcon />}
              </Button>
            ) : null}
          </>
        }
      >
        <div className="space-y-6">
          {step === 2 && (
            <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted-foreground">
              <span>
                Nguồn:{" "}
                <span className="font-medium text-foreground">
                  {source.name}
                </span>
              </span>
              <span>
                Model:{" "}
                <span className="font-medium text-foreground">
                  {model?.name ??
                    model?.filename ??
                    run?.model_id ??
                    "Chưa chọn"}
                </span>
              </span>
            </div>
          )}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p role="status" className="text-sm text-muted-foreground">
              {configureOnly && notice ? notice : message}
              {!configureOnly && run?.counts?.timestamp_ms != null
                ? ` · ${(run.counts.timestamp_ms / 1000).toFixed(2)}s`
                : ""}
            </p>
            {step === 3 && (
              <div className="flex flex-wrap gap-2">{runActions}</div>
            )}
          </div>
          {configureOnly && active && (
            <p role="status" className="text-sm text-muted-foreground">
              Nguồn đang chạy. Chọn “Dừng để chỉnh sửa” hoặc chuyển sang cấu
              hình khác.
            </p>
          )}
          {(error ||
            session.error ||
            run?.error ||
            (run?.counts && !run.counts.valid ? run.counts.reason : null)) && (
            <p role="alert" className="text-sm text-destructive">
              {error || session.error || run?.error || run?.counts?.reason}
            </p>
          )}
          {active && source.kind === "stream" && !connected && counts && (
            <p role="status" className="text-sm text-muted-foreground">
              Không có hình preview. Số đếm vẫn cập nhật từ kết quả AI mới.
            </p>
          )}
          {!configureOnly && notice && (
            <p role="status" className="text-sm text-muted-foreground">
              {notice}
            </p>
          )}
          {aspectChanged && (
            <p role="alert" className="text-sm text-destructive">
              Tỷ lệ khung hình đã đổi. Xoá vùng cũ và vẽ lại.
            </p>
          )}
          {step === 3 && (
            <RunMetrics
              result={run?.result ?? null}
              progress={run?.progress}
              video
            />
          )}
          {step === 3 && (
            <section
              aria-labelledby="counting-results-heading"
              className="space-y-4 rounded-lg border p-4"
            >
              <h3
                id="counting-results-heading"
                className="text-sm font-semibold"
              >
                Số lượng hiện diện
              </h3>
              <div className="space-y-4">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <caption className="sr-only">
                      Số lượng từng class trong mỗi vùng ở frame AI mới nhất
                    </caption>
                    <thead>
                      <tr className="border-b text-left">
                        <th className="min-w-28 p-3">Vùng</th>
                        {displayedClasses.map((key) => (
                          <th key={key} className="min-w-24 p-3 text-right">
                            {countingClassLabel(key)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {displayedZones.map((region) => {
                        const row = counts?.regions.find(
                          (item) => item.id === region.id,
                        );
                        return (
                          <tr
                            key={region.id}
                            className="border-b last:border-0"
                          >
                            <th className="p-3 text-left font-medium">
                              <span
                                className="mr-2 inline-block size-2 rounded-full"
                                style={{ background: region.color }}
                              />
                              {region.name}
                            </th>
                            {displayedClasses.map((key) => (
                              <td
                                key={key}
                                className="p-3 text-right tabular-nums"
                              >
                                {region.classes.includes(key)
                                  ? (row?.counts[key] ?? "—")
                                  : "—"}
                              </td>
                            ))}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                {!counts && (
                  <p role="status" className="text-sm text-muted-foreground">
                    {active && source.kind === "stream"
                      ? "Chưa có dữ liệu mới từ camera/AI. Số lượng tạm thời không khả dụng."
                      : "Số lượng sẽ xuất hiện khi nhận được kết quả AI hợp lệ."}
                  </p>
                )}
                {counts && (
                  <p className="text-xs text-muted-foreground">
                    Frame {counts.frame_id ?? "—"} ·{" "}
                    {((counts.timestamp_ms ?? 0) / 1000).toFixed(2)}s
                    {active
                      ? " · Cập nhật theo AI"
                      : " · Kết quả của frame cuối, không phải tổng lượt"}
                  </p>
                )}
              </div>
            </section>
          )}
          {step === 3 && source.kind === "video" && run?.progress && (
            <div className="space-y-2">
              <div className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground tabular-nums">
                <span>
                  {run.progress.frames_processed} frame đã xử lý · Video gốc{" "}
                  {(run.progress.source_fps ?? 0).toFixed(1)} FPS
                </span>
                <span>
                  {run.progress.percent == null
                    ? ""
                    : `${run.progress.percent.toFixed(1)}%`}
                </span>
              </div>
              {run.progress.percent != null && (
                <div
                  role="progressbar"
                  aria-label="Tiến độ xử lý video"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={run.progress.percent}
                  className="h-1 overflow-hidden rounded bg-muted"
                >
                  <div
                    className="h-full bg-primary transition-[width] motion-reduce:transition-none"
                    style={{ width: `${run.progress.percent}%` }}
                  />
                </div>
              )}
            </div>
          )}
          {regionEditor}
          {step === 2 && canEditRun && (
            <div className="grid items-start gap-6 border-t pt-6 lg:grid-cols-2 lg:gap-8">
              <div className="min-w-0">{classEditor}</div>
              <div className="min-w-0 space-y-6">{parameterEditor}</div>
            </div>
          )}
        </div>
        {step === 3 && (
          <details className="mt-6 border-t pt-6">
            <summary className="cursor-pointer text-sm font-semibold">
              Cấu hình lượt chạy
            </summary>
            <dl className="divide-y pt-4 text-sm">
              {[
                ["Source", source.name],
                [
                  "Model",
                  model?.name ?? model?.filename ?? run?.model_id ?? "—",
                ],
                [
                  "Confidence / IoU",
                  `${run?.options?.conf ?? conf} / ${run?.options?.iou ?? iou}`,
                ],
                ["Thiết bị", run?.options?.device ?? device],
                [
                  promptMode ? "Text prompt YOLOE" : "Class cần đếm",
                  displayedClasses.join(", "),
                ],
                [
                  "Vùng đếm",
                  displayedZones.map((region) => region.name).join(", "),
                ],
              ].map(([label, value]) => (
                <div
                  key={label}
                  className="grid gap-2 py-3 first:pt-0 sm:grid-cols-[11rem_1fr] sm:gap-4"
                >
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd className="min-w-0 break-words font-medium">{value}</dd>
                </div>
              ))}
            </dl>
          </details>
        )}
      </WorkspaceSection>
    </>
  );
}
