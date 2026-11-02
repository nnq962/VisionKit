"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import type { OverlayOptions } from "@/features/vision-overlay";
import { DetectionMedia } from "@/features/vision-overlay";
import type { InferenceResult } from "../api";
import { VideoResultTimeline } from "../video-result-timeline";

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
  const video = useRef<HTMLVideoElement | null>(null);
  const timeline = useRef(new VideoResultTimeline<InferenceResult>());
  const displayed = useRef<InferenceResult | null>(null);
  const [synchronizedResult, setSynchronizedResult] = useState<InferenceResult | null>(null);
  const [blocked, setBlocked] = useState(false);
  const [failed, setFailed] = useState(false);
  const play = useCallback(
    (element: HTMLVideoElement) => {
      element.playbackRate = 1;
      if (element.paused && !element.ended)
        void element.play().catch(() => setBlocked(true));
    },
    [],
  );
  useEffect(() => {
    if (result) timeline.current.push(result, (video.current?.currentTime ?? 0) * 1000);
  }, [result]);
  useEffect(() => {
    let request = 0;
    function update() {
      const element = video.current;
      const next = element && !element.seeking
        ? timeline.current.at(element.currentTime * 1000)
        : null;
      if (displayed.current !== next) {
        displayed.current = next;
        setSynchronizedResult(next);
      }
      request = requestAnimationFrame(update);
    }
    request = requestAnimationFrame(update);
    return () => cancelAnimationFrame(request);
  }, []);
  useEffect(() => {
    const element = video.current;
    if (!element) return;
    if (playing) play(element);
    else element.pause();
  }, [playing, play]);
  return (
    <div className="space-y-3">
      <DetectionMedia
        kind="video"
        src={src}
        label={`Kết quả ${name}`}
        result={synchronizedResult}
        options={options}
        staleAfterMs={0}
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
          },
          onPlaying: () => {
            setBlocked(false);
          },
          onError: () => setFailed(true),
        }}
      />
      {blocked && playing && (
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            video.current && play(video.current)
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
