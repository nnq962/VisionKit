import { useState } from "react";
import { CircleAlertIcon } from "lucide-react";

export function VideoSourcePreview({
  url,
  name,
  poster,
}: {
  url: string;
  name: string;
  poster?: string;
}) {
  const [failed, setFailed] = useState(false);
  return failed ? (
    <div
      role="alert"
      className="flex flex-col items-center gap-2 px-6 text-center text-muted-foreground"
    >
      <CircleAlertIcon className="size-6" />
      <p className="text-sm">Không phát được video</p>
      <p className="text-xs">Thử MP4 với codec H.264 hoặc WebM.</p>
    </div>
  ) : (
    <video
      src={url}
      poster={poster}
      controls
      playsInline
      preload="metadata"
      className="size-full object-contain"
      aria-label={`Xem trước ${name}`}
      onError={() => setFailed(true)}
    />
  );
}
