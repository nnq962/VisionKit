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
    <WorkspacePage
      title="Database"
      description="Quản lý source và model đã lưu."
    >
      <div role="group" aria-label="Loại dữ liệu" className="flex gap-2">
        <Button
          variant={section === "sources" ? "secondary" : "ghost"}
          aria-pressed={section === "sources"}
          onClick={() => setSection("sources")}
        >
          <ImagesIcon />
          Source
        </Button>
        <Button
          variant={section === "models" ? "secondary" : "ghost"}
          aria-pressed={section === "models"}
          onClick={() => setSection("models")}
        >
          <BoxIcon />
          Model
        </Button>
      </div>
      {section === "sources" ? <SourceDatabase /> : <ModelDatabase />}
    </WorkspacePage>
  );
}
