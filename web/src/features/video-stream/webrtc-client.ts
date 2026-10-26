/** WHEP signaling only; RTP media flows directly between MediaMTX and the browser. */
export type CameraStatus = {
  status: "connecting" | "reconnecting" | "ready" | "error";
  auth: "unknown" | "accepted" | "rejected";
  codecs: string[];
  code?: string;
  retryable?: boolean;
  message?: string | null;
};
export class StreamFailure extends Error {
  retryable: boolean;
  code: string;
  constructor(message: string, retryable = true, code = "connection_failed") {
    super(message);
    this.retryable = retryable;
    this.code = code;
  }
}
export type StreamConnection = {
  close: () => void;
  status: (signal: AbortSignal) => Promise<CameraStatus>;
};
export type StreamCallbacks = {
  stream: (stream: MediaStream) => void;
  state: (state: "connected" | "disconnected") => void;
  status: (status: CameraStatus) => void;
  error: (error: StreamFailure) => void;
};

async function request(url: string, options?: RequestInit) {
  const response = await fetch(url, { cache: "no-store", ...options });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new StreamFailure(
      typeof body?.detail === "string" ? body.detail : "Không kết nối được camera.",
      ![400, 401, 403, 404, 409, 422, 429].includes(response.status),
      response.status === 401 ? "auth_failed" : response.status === 410 ? "expired" : "connection_failed",
    );
  }
  return response;
}

function delay(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(new DOMException("Aborted", "AbortError")); };
    const timer = setTimeout(() => { signal.removeEventListener("abort", abort); resolve(); }, ms);
    if (signal.aborted) abort();
    else signal.addEventListener("abort", abort, { once: true });
  });
}

function iceGathered(peer: RTCPeerConnection, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const cleanup = () => {
      clearTimeout(timer);
      peer.removeEventListener("icegatheringstatechange", change);
      signal.removeEventListener("abort", abort);
    };
    const finish = () => { cleanup(); resolve(); };
    const change = () => { if (peer.iceGatheringState === "complete") finish(); };
    const abort = () => { cleanup(); reject(new DOMException("Aborted", "AbortError")); };
    const timer = setTimeout(finish, 5000);
    peer.addEventListener("icegatheringstatechange", change);
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
    else change();
  });
}

export async function openWebRtcStream(
  sourceId: string, callbacks: StreamCallbacks, signal: AbortSignal, temporaryUrl?: string,
): Promise<StreamConnection> {
  if (typeof RTCPeerConnection === "undefined") {
    throw new StreamFailure("Trình duyệt chưa hỗ trợ WebRTC. Thử Chrome hoặc Safari mới.", false, "unsupported_browser");
  }
  const session = await (await request(
    temporaryUrl ? "/api/v1/streams/temporary/sessions" : `/api/v1/streams/${encodeURIComponent(sourceId)}/sessions`,
    temporaryUrl ? {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ preview_id: sourceId, url: temporaryUrl }), signal,
    } : { method: "POST", signal },
  )).json();
  const endpoint = `/api/v1/streams/sessions/${encodeURIComponent(session.id)}`;
  let peer: RTCPeerConnection | null = null;
  let disconnected: ReturnType<typeof setTimeout> | null = null;
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    if (disconnected !== null) clearTimeout(disconnected);
    signal.removeEventListener("abort", close);
    if (peer) {
      peer.ontrack = peer.onconnectionstatechange = null;
      peer.close();
    }
    void fetch(endpoint, { method: "DELETE", keepalive: true }).catch(() => {});
  };
  signal.addEventListener("abort", close, { once: true });
  const status = async (readSignal: AbortSignal): Promise<CameraStatus> =>
    (await request(endpoint, { signal: readSignal })).json();
  try {
    if (signal.aborted) throw new DOMException("Aborted", "AbortError");
    for (;;) {
      const camera = await status(signal);
      callbacks.status(camera);
      if (camera.status === "error") throw new StreamFailure(camera.message ?? "Camera từ chối kết nối.", camera.retryable ?? false, camera.code);
      if (camera.status === "ready") {
        const videoCodecs = camera.codecs.filter((codec) => ["H264", "H265", "VP8", "VP9", "AV1", "M-JPEG", "MPEG-4 Video"].includes(codec));
        const supported = RTCRtpReceiver.getCapabilities("video")?.codecs.map((codec) => codec.mimeType.toUpperCase()) ?? [];
        if (videoCodecs.length && !videoCodecs.some((codec) => supported.includes(`VIDEO/${codec}`))) {
          throw new StreamFailure(`Trình duyệt không hỗ trợ codec ${videoCodecs.join(", ")}. Chuyển camera sang H.264 không B-frame.`, false, "unsupported_codec");
        }
        break;
      }
      await delay(1000, signal);
    }
    peer = new RTCPeerConnection({ iceServers: [] });
    const media = new MediaStream();
    peer.ontrack = (event) => {
      if (closed) return;
      for (const track of event.streams[0]?.getTracks() ?? [event.track]) {
        if (!media.getTracks().some((existing) => existing.id === track.id)) media.addTrack(track);
      }
      callbacks.stream(media);
    };
    peer.onconnectionstatechange = () => {
      if (closed || !peer) return;
      if (disconnected !== null) { clearTimeout(disconnected); disconnected = null; }
      if (peer.connectionState === "connected") callbacks.state("connected");
      else if (peer.connectionState === "failed") callbacks.error(new StreamFailure("Kết nối WebRTC bị gián đoạn. Đang thử lại…"));
      else if (peer.connectionState === "disconnected") {
        callbacks.state("disconnected");
        disconnected = setTimeout(() => callbacks.error(new StreamFailure("Mất kết nối WebRTC. Đang thử lại…")), 10000);
      }
    };
    peer.addTransceiver("video", { direction: "recvonly" });
    peer.addTransceiver("audio", { direction: "recvonly" });
    await peer.setLocalDescription(await peer.createOffer());
    await iceGathered(peer, signal);
    const answer = await request(`${endpoint}/whep`, {
      method: "POST", headers: { "Content-Type": "application/sdp" },
      body: peer.localDescription?.sdp, signal,
    });
    await peer.setRemoteDescription({ type: "answer", sdp: await answer.text() });
    if (closed || signal.aborted) throw new DOMException("Aborted", "AbortError");
    return { close, status };
  } catch (error) {
    close();
    throw error;
  }
}
