import { PlusIcon, Settings2Icon } from "lucide-react";
import { useState } from "react";
import { inspectRtspUrl } from "../rtsp-configuration";
import { useVideoStream } from "@/features/video-stream";
import { Button } from "@/components/ui/button";
import { RtspCameraForm } from "./rtsp-camera-form";
import { SavedSourceActions } from "./saved-source-actions";
import type { SourceSelection } from "../use-source-selection";

export function RtspSourceInput({ selection }: { selection: SourceSelection }) {
  const source = selection.source;
  const [actions, setActions] = useState(false);
  const preview = useVideoStream(source?.streamPreview ? source.id : null, { autoConnect: false });
  const checking = ["connecting", "reconnecting"].includes(preview.status);
  if (source?.saved && source.kind === "stream") {
    return (
      <div className="space-y-6">
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">{source.name}</h3>
          <p className="break-all text-sm text-muted-foreground">{source.location}</p>
          <p className="text-xs text-muted-foreground">Đã lưu trong thư viện camera.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" disabled={selection.saving} onClick={() => setActions(!actions)} aria-expanded={actions}>
            <Settings2Icon /> Quản lý camera
          </Button>
          <Button variant="ghost" disabled={selection.saving} onClick={() => { selection.discardDraft(); setActions(false); }}>
            <PlusIcon /> Thêm camera khác
          </Button>
        </div>
        {actions && <SavedSourceActions key={source.id} source={source} selection={selection} />}
      </div>
    );
  }
  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h3 className="text-sm font-semibold">Kết nối camera IP</h3>
        <p className="text-xs leading-5 text-muted-foreground">Kiểm tra kết nối và xem trực tiếp. Không cần lưu vào thư viện.</p>
      </div>
      <RtspCameraForm
        initialName={selection.saveName} initialUrl={selection.location}
        busy={selection.saving}
        onDraftChange={selection.updateRtspDraft}
        onCheck={selection.checkRtsp}
        checking={checking}
        canSave={!inspectRtspUrl(selection.location).error}
        onSave={(name, url) => selection.configureRtsp(name, url)}
      />
    </div>
  );
}
