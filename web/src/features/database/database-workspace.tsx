"use client";

import { useState } from "react";
import { BoxIcon, ImagesIcon } from "lucide-react";
import { WorkspacePage } from "@/components/workspace-page";
import { Button } from "@/components/ui/button";
import { SourceDatabase } from "./source-database";
import { ModelDatabase } from "./model-database";

export function DatabaseWorkspace() {
  const [section, setSection] = useState<"sources" | "models">("sources");
  return (
    <WorkspacePage title="Database" hideHeading>
      <div className="space-y-6">
        <div
          role="group"
          aria-label="Loại dữ liệu"
          className="inline-flex max-w-full flex-wrap gap-1 rounded-lg bg-muted/60 p-1"
        >
          <Button
            variant={section === "sources" ? "outline" : "ghost"}
            aria-pressed={section === "sources"}
            onClick={() => setSection("sources")}
          >
            <ImagesIcon />
            Nguồn
          </Button>
          <Button
            variant={section === "models" ? "outline" : "ghost"}
            aria-pressed={section === "models"}
            onClick={() => setSection("models")}
          >
            <BoxIcon />
            Model
          </Button>
        </div>
        {section === "sources" ? <SourceDatabase /> : <ModelDatabase />}
      </div>
    </WorkspacePage>
  );
}
