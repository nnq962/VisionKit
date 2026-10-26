"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import type { OverlayOptions } from "@/features/vision-overlay";
import { DetectionMedia } from "@/features/vision-overlay";
import type { InferenceResult } from "../api";

export function VideoRunPreview({
  src,
  name,
  poster,
  result,
  playing,
  options,
}: {
  src: string;
  name: string;
  poster?: string;
  result: InferenceResult | null;
  playing: boolean;
  options?: OverlayOptions;
}) {
  const positioned = useRef(false);
  const video = useRef<HTMLVideoElement | null>(null);
  const [blocked, setBlocked] = useState(false);
  const [failed, setFailed] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [stillFrame, setStillFrame] = useState<string | number | null>(null);
  const timestamp = result?.timestampMs ?? 0;
  const play = useCallback(
    (element: HTMLVideoElement) => {
      if (!positioned.current && element.readyState >= 1) {
        element.currentTime = Math.max(0, timestamp / 1000);
        positioned.current = true;
      }
      if (element.paused && !element.ended)
        void element.play().catch(() => setBlocked(true));
    },
    [timestamp],
  );
  useEffect(() => {
    const element = video.current;
    if (!element) return;
    if (playing) play(element);
    else {
      element.pause();
      if (result && element.readyState >= 1)
        element.currentTime = Math.max(0, timestamp / 1000);
    }
  }, [playing, play, result, timestamp]);
  return (
    <div className="space-y-3">
      <DetectionMedia
        kind="video"
        src={src}
        label={`Kết quả ${name}`}
        result={
          (playing && isPlaying) ||
          (!playing && stillFrame === (result?.frameId ?? 0))
            ? result
            : null
        }
        options={options}
        staleAfterMs={2000}
        className="rounded-lg"
        videoProps={{
          controls: false,
          muted: true,
          playsInline: true,
          preload: "auto",
          poster,
          onLoadedMetadata: (event) => {
            video.current = event.currentTarget;
            if (playing) play(event.currentTarget);
            else if (result)
              event.currentTarget.currentTime = Math.max(0, timestamp / 1000);
          },
          onPlaying: () => {
            setStillFrame(null);
            setIsPlaying(true);
            setBlocked(false);
          },
          onPause: () => setIsPlaying(false),
          onSeeking: () => setStillFrame(null),
          onSeeked: (event) => {
            if (
              !playing &&
              result &&
              Math.abs(event.currentTarget.currentTime - timestamp / 1000) <
                0.15
            )
              setStillFrame(result.frameId ?? 0);
          },
          onEnded: () => setIsPlaying(false),
          onError: () => setFailed(true),
        }}
      />
      {blocked && playing && (
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            void video.current?.play().catch(() => setBlocked(true))
          }
        >
          Phát video
        </Button>
      )}
      {failed && (
        <p role="alert" className="text-xs text-destructive">
          Trình duyệt không phát được codec này. Thử video MP4/H.264.
        </p>
      )}
    </div>
  );
}
