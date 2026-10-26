# Persistent MediaMTX / WebRTC preview

Camera RTSP/TCP → MediaMTX → WebRTC → native `<video>`. MediaMTX forwards encoded
media; preview does not decode/transcode on the server and does not send JPEGs
through Python/WebSockets. Camera H.264 without B-frames is the practical browser
setting. H.265 and other codecs depend on browser support; the UI reports a codec
error rather than starting a transcode. Video plays muted by default.

`VideoStreamProvider` is mounted in `app/layout.tsx`. It owns one RTCPeerConnection
and MediaStream per saved camera ID, shared by all hook consumers in the tab.
Unmounting a consumer, changing pipeline steps and Next.js route navigation only
unsubscribe the component. The provider keeps the peer alive until explicit stop
or app teardown. Reload creates a new browser session.

```tsx
"use client";
import { useEffect, useRef } from "react";
import { useVideoStream } from "@/features/video-stream";

export function Camera({ sourceId }: { sourceId: string }) {
  const video = useRef<HTMLVideoElement>(null);
  const { mediaStream, status, auth, error, stop, reconnect } = useVideoStream(sourceId);
  useEffect(() => {
    const element = video.current;
    if (!element) return;
    element.srcObject = mediaStream;
    return () => { element.srcObject = null; };
  }, [mediaStream]);
  return <>
    <video ref={video} autoPlay muted playsInline />
    <p>{error ?? `${status} / ${auth}`}</p>
    <button onClick={stop}>Stop</button>
    <button onClick={reconnect}>Reconnect</button>
  </>;
}
```

`VideoStreamPreview` is the existing reusable viewer with controls and status.
The RTSP form first checks an unsaved URL through
`POST /api/v1/streams/temporary/sessions` with `{preview_id, url}`. The provider
registers that local preview ID using `startTemporary(id, url)`; ordinary hook
consumers then share its connection exactly as for a saved camera. Authentication
and codec validation finish before the WebRTC offer, so an invalid camera never
shows video. Names are optional and no Source-library API is called until the
user explicitly selects “Lưu vào thư viện”.

Temporary URL configurations live only in backend RAM/MediaMTX, use their own
path namespace and share the same four-camera limit. Stop/expiry removes their
URL and path after the last lease. Editing the URL or discarding a draft closes
the old temporary connection; route changes keep it. Browser draft restoration
keeps form input but does not auto-open an unsaved preview after a full reload.
The first check stops with an actionable error after 35 seconds; an established
live connection retains automatic reconnect behavior.

`sourceId: null` never connects. `autoConnect: false` disables automatic startup
without stopping an already-shared connection. `stop()` persists the stopped state
across routes; `connect()`/`reconnect()` explicitly resume it. Changing sourceId
keeps the old source connected until explicitly stopped. Up to four camera paths
are active per backend; all browser tabs use the same MediaMTX path for a source.

## Signaling, status and lifetime

1. POST `/api/v1/streams/{sourceId}/sessions` registers the saved RTSP URL on the
   internal Control API, then returns a random viewer lease ID.
2. GET `/api/v1/streams/sessions/{id}` waits for readable media and reports auth
   and codecs. During playback it also renews the lease every two seconds.
3. Browser gathers ICE candidates, POSTs SDP to `/sessions/{id}/whep`, and receives
   the MediaMTX answer. Backend holds the upstream WHEP session URL. Media flows
   directly over ICE/DTLS/SRTP; Python handles signaling and small JSON only.
4. Stop aborts pending signaling, closes the peer and DELETEs the lease/WHEP session.
   The last viewer removes the MediaMTX path and disconnects RTSP. Abrupt browser
   loss expires its lease after 45 seconds, swept every five seconds.

Auth `accepted` means MediaMTX has readable media (`available/ready`), including
anonymous cameras. It does not independently prove a password was required.
Auth `rejected` is based on 401/403 or explicit authentication failure in the
static-source `lastError` API. `online` alone does not establish success. Raw
source errors and camera credentials never appear in public status responses.
The form's account-in-URL summary is separate from this real connection check.

MediaMTX reconnects the camera source. The store retries failed signaling/peers
with exponential backoff (1–30 seconds ±20% jitter), a 35-second negotiation limit,
and a 10-second disconnected grace period. Backend heartbeat failures also retry;
network online accelerates recovery. Auth/unsupported-codec errors are terminal
until explicit retry or a URL configuration change. Late responses from old
connections are ignored and late successful peer sessions are closed.

Editing a camera URL updates its MediaMTX path; active local viewers renegotiate.
Stopped viewers stay stopped. Inference still has its own reader and is independent
of preview; preview timestamps are not synchronized with detection overlays.

## Relay setup and networking

Start Docker Desktop, run `docker compose pull mediamtx`, then `./dev.py`.
`compose.yaml` uses the official v1.21.3 image pinned by digest. The launcher owns
its Compose project and removes that relay container/network when stopped.
There is no local MediaMTX executable or installer. `--no-media` uses external
MediaMTX at the backend's `VISIONKIT_MEDIAMTX_API_URL` / `VISIONKIT_MEDIAMTX_WEBRTC_URL`.

`media/mediamtx.yml` is mounted read-only. API/WHEP/RTSP/ICE listeners bind inside
the container; Compose publishes only on host loopback. The launcher maps source
loopback URLs to `host.docker.internal` internally without changing saved URLs.
For remote users configure reachable ICE hosts/listeners and TURN as needed;
an HTTP reverse proxy alone does not forward WebRTC media. Keep Control API private.
Do not share the application's `visionkit_*` relay namespace between independent
backend instances. Run one backend worker for the in-memory lease registry.
MediaMTX runtime logs are discarded; backend returns only safe classified errors.

## Checks

- `npm run test:streams`: peer sharing, routes, recovery, auth terminal errors,
  stale negotiation, explicit stop, resource limits and disposal.
- `.venv/bin/python -m unittest tests.streams.test_preview -v` (cwd backend):
  API/lease/WHEP/redaction contracts using mocked internal HTTP.
- `.venv/bin/python -m unittest tests.streams.test_mediamtx_integration -v`
  (cwd backend, set `VISIONKIT_RUN_DOCKER_TESTS=1`): MediaMTX Docker and RTSP H264 Basic-auth fixture on isolated
  ports. FFmpeg generates a tiny fixture then exits before relay tests run.

The real browser smoke check also verified decoded H264 video, one peer across
routes, actual 401 failure/correction and peer closure after stop. Physical camera,
RTSPS/TLS and multi-hour network soak require additional validation.
