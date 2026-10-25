"use client";

import { useState } from "react";
import { ArrowLeftIcon, ArrowRightIcon, CheckIcon } from "lucide-react";
import { WorkspacePage, WorkspaceSection } from "@/components/workspace-page";
import { Button } from "@/components/ui/button";
import { useModelSelection } from "@/features/models/model-selection-provider";
import { useSourceSelection } from "@/features/sources/source-provider";
import { SourceStep } from "./steps/source-step";
import { ModelStep } from "./steps/model-step";
import { ParametersStep } from "./steps/parameters-step";
import { RunStep } from "./steps/run-step";
import { defaultParameters } from "./types";
import { validateStep } from "./validation";

const steps = ["Chọn source", "Chọn model", "Thông số", "Chạy"];

export function YoloPipeline() {
  const [step, setStep] = useState(0);
  const selection = useSourceSelection();
  const modelSelection = useModelSelection();
  const model = modelSelection.selected;
  const [parameters, setParameters] = useState(defaultParameters);
  const [error, setError] = useState("");
  const [errorSourceId, setErrorSourceId] = useState<string | null>(null);

  async function next() {
    let message = validateStep(step, selection.source, model, parameters);
    if (step === 1 && modelSelection.mode === "upload")
      message = "Lưu và chọn model trước khi tiếp tục.";
    if (step === 0 && !message && selection.saveEnabled) {
      if (!selection.saveName.trim()) message = "Đặt tên source trước khi lưu.";
      else if (!(await selection.save())) return;
    }
    if (step === 1 && !message && !(await modelSelection.validate())) return;
    setErrorSourceId(selection.source?.id ?? null);
    setError(message);
    if (!message) setStep((current) => Math.min(current + 1, steps.length - 1));
  }

  return (
    <WorkspacePage
      title="YOLO pipeline"
      description="Thiết lập nguồn dữ liệu, model và thông số cho tác vụ nhận diện."
    >
      <ol
        aria-label="Các bước thiết lập"
        className="grid grid-cols-2 gap-3 sm:grid-cols-4"
      >
        {steps.map((title, index) => (
          <li
            key={title}
            aria-current={step === index ? "step" : undefined}
            className={`flex items-center gap-2 border-b-2 pb-3 text-sm ${step === index ? "border-primary font-semibold" : "border-border text-muted-foreground"}`}
          >
            <span
              className={`flex size-6 shrink-0 items-center justify-center rounded-full text-xs ${step === index ? "bg-primary text-primary-foreground" : "bg-muted"}`}
            >
              {step > index ? <CheckIcon className="size-3" /> : index + 1}
            </span>
            {title}
          </li>
        ))}
      </ol>
      <WorkspaceSection
        title={steps[step]}
        titleId="step-heading"
        footer={
          <>
            <Button
              variant="outline"
              disabled={
                step === 0 ||
                selection.saving ||
                modelSelection.uploading ||
                modelSelection.validating
              }
              onClick={() => {
                setStep((current) => current - 1);
                setError("");
              }}
            >
              <ArrowLeftIcon data-icon="inline-start" />
              Quay lại
            </Button>
            {step < 3 && (
              <Button
                onClick={() => void next()}
                disabled={
                  selection.saving ||
                  modelSelection.uploading ||
                  modelSelection.validating ||
                  (step === 1 &&
                    ["queued", "processing"].includes(
                      model?.inspection.status ?? "",
                    )) ||
                  !selection.draftsReady ||
                  (step === 0 && selection.source?.status === "loading")
                }
              >
                Tiếp tục
                <ArrowRightIcon data-icon="inline-end" />
              </Button>
            )}
          </>
        }
      >
        {step === 0 && <SourceStep selection={selection} />}
        {step === 1 && <ModelStep selection={modelSelection} />}
        {step === 2 && (
          <ParametersStep parameters={parameters} onChange={setParameters} />
        )}
        {step === 3 && (
          <RunStep
            source={selection.source?.name ?? ""}
            model={model?.name ?? model?.filename ?? ""}
            parameters={parameters}
          />
        )}
        {error &&
          (step !== 1 || !model || modelSelection.mode === "upload") &&
          (step !== 0 || errorSourceId === (selection.source?.id ?? null)) && (
            <p role="alert" className="mt-6 text-sm text-destructive">
              {error}
            </p>
          )}
      </WorkspaceSection>
    </WorkspacePage>
  );
}
