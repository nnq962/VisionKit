"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowRightIcon,
  CheckIcon,
  LoaderCircleIcon,
  PlayIcon,
} from "lucide-react";
import { WorkspacePage, WorkspaceSection } from "@/components/workspace-page";
import { Button } from "@/components/ui/button";
import { useModelSelection } from "@/features/models/model-selection-provider";
import { useSourceSelection } from "@/features/sources/source-provider";
import type { RunNavigation } from "@/features/inference/components/run-workspace";
import { SourceStep } from "./steps/source-step";
import { ModelStep } from "./steps/model-step";
import { ParametersStep } from "./steps/parameters-step";
import { RunStep } from "./steps/run-step";
import { usePipelineParameters } from "./use-pipeline-parameters";
import { validateStep } from "./validation";

const steps = ["Nguồn", "Model", "Thông số", "Kết quả"];
const headings = [
  "Nguồn đầu vào",
  "Model nhận diện",
  "Thông số nhận diện",
  "Chạy AI",
];

export function YoloPipeline() {
  const [step, setStep] = useState(0);
  const [runToolbar, setRunToolbar] = useState<HTMLDivElement | null>(null);
  const runNavigation = useRef<RunNavigation>(null);
  const navigating = useRef(false);
  const [checking, setChecking] = useState(false);
  const [showChecking, setShowChecking] = useState(false);
  const [startRequested, setStartRequested] = useState(false);
  const [runBusy, setRunBusy] = useState(false);
  const selection = useSourceSelection();
  const modelSelection = useModelSelection();
  const model = modelSelection.selected;
  const {
    parameters,
    update: setParameters,
    storageError,
  } = usePipelineParameters(model);
  const [error, setError] = useState("");
  const sourceReady = !validateStep(0, selection.source, model, parameters);
  const modelReady = Boolean(
    model && ["ready", "manual"].includes(model.inspection.status),
  );
  const busy =
    checking ||
    selection.saving ||
    modelSelection.uploading ||
    modelSelection.saving ||
    modelSelection.validating ||
    runBusy;

  useEffect(() => {
    if (!checking) return;
    const timer = setTimeout(() => setShowChecking(true), 200);
    return () => clearTimeout(timer);
  }, [checking]);

  function showStep(target: number, start = false) {
    setError("");
    setStartRequested(start);
    setStep(target);
  }

  async function navigate(target: number, start = false) {
    if (target === step || busy || navigating.current) return;
    if (step === 3) {
      runNavigation.current?.requestEdit(target);
      return;
    }
    if (target < step) {
      showStep(target);
      return;
    }
    navigating.current = true;
    setError("");
    try {
      // Source and model can be chosen in either order; running validates both.
      const prerequisites = target === 3 ? [0, 1, 2] : target === 2 ? [1] : [];
      for (const current of prerequisites) {
        const message = validateStep(
          current,
          selection.source,
          model,
          parameters,
        );
        if (message) {
          showStep(current);
          setError(message);
          return;
        }
      }
      if (target === 3) {
        setChecking(true);
        if (!(await modelSelection.validate())) {
          showStep(1);
          return;
        }
      }
      showStep(target, start);
    } finally {
      navigating.current = false;
      setChecking(false);
      setShowChecking(false);
    }
  }

  async function complete() {
    const resetSource = await selection.finishCurrent();
    const resetModel = await modelSelection.finishTemporary();
    resetSource();
    resetModel();
    showStep(0);
  }

  const summaries = [
    selection.source?.name ?? "Chọn ảnh, video hoặc camera",
    model?.name ?? model?.filename ?? "Chọn model",
    `${parameters.confidence} conf · ${parameters.imageSize} px`,
    "Xem và lưu kết quả",
  ];
  const nextStep = step > 0 && !sourceReady ? 0 : !modelReady ? 1 : 3;

  return (
    <WorkspacePage title="YOLO pipeline" hideHeading>
      <div className="space-y-6">
        <nav aria-label="Thiết lập pipeline" className="shrink-0">
          <ol className="grid grid-cols-4 gap-1 sm:gap-2">
            {steps.map((title, index) => {
              const current = step === index;
              const disabled =
                busy ||
                !selection.draftsReady ||
                !modelSelection.draftsReady ||
                (index === 2 && !modelReady) ||
                (index === 3 && (!sourceReady || !modelReady));
              const ready =
                index === 0
                  ? sourceReady
                  : index === 1
                    ? modelReady
                    : index === 2
                      ? modelReady &&
                        !validateStep(2, selection.source, model, parameters)
                      : false;
              return (
                <li key={title} className="min-w-0">
                  <button
                    type="button"
                    aria-current={current ? "step" : undefined}
                    aria-label={title}
                    disabled={disabled}
                    onClick={() => void navigate(index)}
                    className={`flex w-full min-w-0 items-center justify-center gap-2 rounded-lg px-2 py-3 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed sm:justify-start sm:px-3 ${disabled && !checking && !runBusy ? "opacity-45" : ""} ${current ? "bg-primary/8 text-accent-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}
                  >
                    <span
                      className={`hidden size-7 shrink-0 items-center justify-center rounded-full text-xs font-medium sm:flex ${current ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"}`}
                    >
                      {ready && !current ? (
                        <CheckIcon className="size-3.5" />
                      ) : (
                        index + 1
                      )}
                    </span>
                    <span className="min-w-0">
                      <span className="block text-xs font-semibold sm:text-sm">
                        {title}
                      </span>
                      <span
                        className="mt-0.5 hidden truncate text-xs text-muted-foreground lg:block"
                        title={summaries[index]}
                      >
                        {summaries[index]}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>
        <WorkspaceSection
          title={headings[step]}
          titleId="step-heading"
          showHeader={false}
          variant="plain"
          toolbar={
            <div className="flex w-full min-w-0 flex-wrap items-center justify-between gap-3">
              <div
                ref={setRunToolbar}
                className={step === 3 ? "w-full min-w-0" : "hidden"}
              />
              {step !== 3 && (
                <>
                  <span className="text-sm font-semibold">
                    {headings[step]}
                  </span>
                  <Button
                    size="lg"
                    className={`min-w-36 ${checking ? "disabled:opacity-100" : ""}`}
                    aria-busy={checking}
                    disabled={
                      busy ||
                      !selection.draftsReady ||
                      !modelSelection.draftsReady ||
                      (step === 0 && !sourceReady) ||
                      (step === 1 && !modelReady)
                    }
                    onClick={() => void navigate(nextStep, nextStep === 3)}
                  >
                    {showChecking ? (
                      <LoaderCircleIcon className="animate-spin motion-reduce:animate-none" />
                    ) : nextStep === 3 ? (
                      <PlayIcon />
                    ) : (
                      <ArrowRightIcon />
                    )}
                    {nextStep === 0
                      ? "Chọn nguồn"
                      : nextStep === 1
                        ? "Chọn model"
                        : "Chạy AI"}
                  </Button>
                </>
              )}
            </div>
          }
        >
          {error && (
            <p role="alert" className="mb-4 text-sm text-destructive">
              {error}
            </p>
          )}
          {step === 0 && <SourceStep selection={selection} />}
          {step === 1 && <ModelStep selection={modelSelection} />}
          {step === 2 && (
            <ParametersStep
              parameters={parameters}
              onChange={(value) => {
                setParameters(value);
                setError("");
              }}
              source={selection.source}
              model={model}
              storageError={storageError}
            />
          )}
          {step === 3 && (
            <RunStep
              source={selection.source?.name ?? ""}
              model={model?.name ?? model?.filename ?? ""}
              parameters={parameters}
              sourceKind={selection.source?.kind}
              modelRecord={model}
              sourceRecord={selection.source}
              onComplete={complete}
              controlsTarget={runToolbar}
              navigationRef={runNavigation}
              onNavigate={showStep}
              onBusyChange={setRunBusy}
              autoStart={startRequested}
            />
          )}
        </WorkspaceSection>
      </div>
    </WorkspacePage>
  );
}
