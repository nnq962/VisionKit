import { useState } from "react";
import { PencilIcon, Settings2Icon, Trash2Icon } from "lucide-react";
import { RtspCameraForm } from "./rtsp-camera-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { VisionSource } from "../types";
import type { SourceSelection } from "../use-source-selection";

export function SavedSourceActions({
  source,
  selection,
}: {
  source: VisionSource;
  selection: Pick<SourceSelection, "saving" | "rename" | "remove" | "configureRtsp">;
}) {
  const [mode, setMode] = useState<"view" | "rename" | "delete" | "configure">("view");
  const [name, setName] = useState(source.name);
  return (
    <div className="space-y-3 px-3 pb-4">
      {mode === "view" ? (
        <div className="flex flex-wrap gap-2">
          {source.kind === "stream" && <Button variant="ghost" size="sm" disabled={selection.saving} onClick={() => setMode("configure")}>
            <Settings2Icon /> Sửa cấu hình
          </Button>}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setName(source.name);
              setMode("rename");
            }}
            disabled={selection.saving}
          >
            <PencilIcon />
            Đổi tên
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setMode("delete")}
            disabled={selection.saving}
          >
            <Trash2Icon />
            Xoá
          </Button>
        </div>
      ) : mode === "configure" ? (
        <RtspCameraForm
          initialName={source.name} currentLocation={source.location} busy={selection.saving}
          onCancel={() => setMode("view")}
          onSave={async (nextName, url) => {
            const ok = await selection.configureRtsp(nextName, url, source.id);
            if (ok) setMode("view");
            return ok;
          }}
        />
      ) : mode === "rename" ? (
        <form
          className="space-y-2"
          onSubmit={async (event) => {
            event.preventDefault();
            if (await selection.rename(source.id, name.trim())) setMode("view");
          }}
        >
          <Label htmlFor={`rename-${source.id}`}>Tên source mới</Label>
          <Input
            id={`rename-${source.id}`}
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={120}
            disabled={selection.saving}
            autoFocus
          />
          <div className="flex gap-2">
            <Button size="sm" disabled={!name.trim() || selection.saving}>
              Lưu tên
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setMode("view")}
              disabled={selection.saving}
            >
              Huỷ
            </Button>
          </div>
        </form>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-destructive">
            {source.kind === "stream" ? "Xoá cấu hình camera này khỏi thư viện?" : "Xoá source này và file đã lưu trên máy?"}
          </p>
          <div className="flex gap-2">
            <Button
              variant="destructive"
              size="sm"
              disabled={selection.saving}
              onClick={async () => {
                if (await selection.remove(source.id)) setMode("view");
              }}
            >
              Xác nhận xoá
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setMode("view")}
              disabled={selection.saving}
            >
              Huỷ
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
