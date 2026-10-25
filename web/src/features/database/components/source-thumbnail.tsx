/* eslint-disable @next/next/no-img-element */
import { useState } from "react";
import { FileImageIcon, FilmIcon, RadioIcon } from "lucide-react";
import type { VisionSource } from "@/features/sources/types";

export function SourceThumbnail({ source }: { source: VisionSource }) {
  const [failed, setFailed] = useState(false);
  const url =
    source.kind === "video"
      ? source.thumbnailUrl
      : ["image", "screen"].includes(source.kind)
        ? source.previewUrl
        : undefined;
  const Icon =
    source.kind === "video"
      ? FilmIcon
      : ["image", "screen"].includes(source.kind)
        ? FileImageIcon
        : RadioIcon;
  return (
    <span className="flex h-12 w-16 shrink-0 items-center justify-center overflow-hidden rounded-md bg-muted">
      {url && !failed ? (
        <img
          src={url}
          alt=""
          loading="lazy"
          className="size-full object-cover"
          onError={() => setFailed(true)}
        />
      ) : (
        <Icon className="size-5 text-muted-foreground" strokeWidth={1.5} />
      )}
    </span>
  );
}
