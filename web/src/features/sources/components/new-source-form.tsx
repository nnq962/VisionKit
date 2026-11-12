import { useState } from "react";
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
import { RtspSourceInput } from "./rtsp-source-input";
import { FileSourceInput } from "./file-source-input";
import { BrowserSourceInput } from "./browser-source-input";
import { sourceKinds, type SourceKind } from "../types";
import type { SourceSelection } from "../use-source-selection";

export function NewSourceForm({
  selection,
  allowedKinds,
}: {
  selection: SourceSelection;
  allowedKinds?: SourceKind[];
}) {
  const { kind, location } = selection;
  const [error, setError] = useState("");
  const isFile = kind === "image" || kind === "video";
  const hint = sourceKinds.find((item) => item.value === kind)!.hint;

  function useYoutubeLocation() {
    setError("");
    const value = location.trim();
    try {
      const url = new URL(value);
      const valid =
        ["http:", "https:"].includes(url.protocol) &&
        [
          "youtube.com",
          "www.youtube.com",
          "m.youtube.com",
          "youtu.be",
        ].includes(url.hostname) &&
        (url.hostname === "youtu.be"
          ? url.pathname.length > 1
          : Boolean(url.searchParams.get("v")) ||
            /^\/(shorts|live|embed)\/.+/.test(url.pathname));
      if (!valid) throw new Error();
    } catch {
      setError("Nhập URL video YouTube hợp lệ.");
      return;
    }
    void selection.selectYoutube(value);
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Label htmlFor="source-kind">Loại nguồn</Label>
        <Select
          disabled={selection.saving}
          value={kind}
          onValueChange={(value) => {
            selection.setKind(value as SourceKind);
            setError("");
          }}
        >
          <SelectTrigger id="source-kind" className="h-9 w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {sourceKinds
                .filter(
                  (item) => !allowedKinds || allowedKinds.includes(item.value),
                )
                .map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
            </SelectGroup>
          </SelectContent>
        </Select>
        {!isFile && (
          <p className="text-xs leading-5 text-muted-foreground">{hint}</p>
        )}
      </div>
      {kind === "stream" ? (
        <RtspSourceInput selection={selection} />
      ) : kind === "image" || kind === "video" ? (
        <FileSourceInput key={kind} selection={selection} kind={kind} />
      ) : kind === "webcam" || kind === "screen" ? (
        <BrowserSourceInput kind={kind} selection={selection} />
      ) : (
        <div className="space-y-2">
          <Label htmlFor="source-location">URL video YouTube</Label>
          <Input
            id="source-location"
            className="h-9"
            value={location}
            onChange={(event) => {
              selection.setLocation(event.target.value);
              setError("");
            }}
            placeholder="https://www.youtube.com/watch?v=…"
            inputMode="url"
          />
          <p className="text-xs leading-5 text-muted-foreground">
            Video thường · tối đa 720p, 200 MiB · bản tạm tự hết hạn.
          </p>
          <Button
            type="button"
            variant="outline"
            className="mt-2"
            onClick={useYoutubeLocation}
          >
            {selection.source?.status === "loading"
              ? "Chuẩn bị lại video"
              : "Chuẩn bị video"}
          </Button>
          {selection.source?.kind === "youtube" && (
            <div className="space-y-2 pt-2">
              {selection.source.status === "loading" && (
                <p role="status" className="text-sm text-muted-foreground">
                  Đang chuẩn bị video YouTube…
                </p>
              )}
              {selection.source.status === "ready" && (
                <p role="status" className="text-sm text-muted-foreground">
                  Video sẵn sàng.
                </p>
              )}
              {selection.source.error && (
                <p role="alert" className="text-sm text-destructive">
                  {selection.source.error}
                </p>
              )}
              <Button
                variant="destructive"
                onClick={() => void selection.discardYoutube()}
              >
                {selection.source.status === "loading"
                  ? "Huỷ chuẩn bị"
                  : "Xoá video tạm"}
              </Button>
            </div>
          )}
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
