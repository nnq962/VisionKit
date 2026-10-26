"use client";

import { useEffect, useRef, useState } from "react";
import { useVideoStreamStore } from "@/features/video-stream/video-stream-provider";
import { useSourceLibrary } from "./use-source-library";
import { useSourceDrafts } from "./use-source-drafts";
import { captureScreenFrame } from "./browser-capture";
import { inspectRtspUrl } from "./rtsp-configuration";
import { readMediaMetadata } from "./media-metadata";
import { configureRtspSource, deleteSource, inspectImage, renameSource, saveSource } from "./api";
import type { SourceKind, VisionSource } from "./types";

export function useSourceSelectionState() {
  const videoStreams = useVideoStreamStore();
  const drafts = useSourceDrafts();
  const { source, saveName, saveEnabled } = drafts;
  const savedSources = useSourceLibrary();
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [notice, setNotice] = useState("");
  const mutation = useRef(false);
  const active = useRef(true);
  const urls = useRef(new Set<string>());
  const streams = useRef(new Set<MediaStream>());
  const liveCamera = useRef<VisionSource | null>(null);
  const cameraRequest = useRef(0);

  useEffect(() => {
    active.current = true;
    const ownedUrls = urls.current;
    const ownedStreams = streams.current;
    return () => {
      active.current = false;
      ownedUrls.forEach((url) => URL.revokeObjectURL(url));
      ownedUrls.clear();
      ownedStreams.forEach((stream) =>
        stream.getTracks().forEach((track) => track.stop()),
      );
      ownedStreams.clear();
    };
  }, []);

  function isCurrent(source: VisionSource) {
    return active.current && drafts.isCurrent(source);
  }

  function stopCamera() {
    cameraRequest.current++;
    const camera = liveCamera.current;
    if (!camera) return;
    liveCamera.current = null;
    camera.mediaStream?.getTracks().forEach((track) => track.stop());
    if (camera.mediaStream) streams.current.delete(camera.mediaStream);
    drafts.publish({ ...camera, mediaStream: undefined, status: "pending" });
  }

  function clearFeedback() {
    setNotice("");
    setSaveError("");
  }

  function begin(next: VisionSource) {
    stopCamera();
    drafts.begin(next);
    clearFeedback();
  }

  function select(next: VisionSource | null) {
    stopCamera();
    drafts.select(next);
    clearFeedback();
  }

  function setMode(mode: "new" | "saved") {
    stopCamera();
    drafts.setMode(mode);
    clearFeedback();
  }
  function setKind(kind: SourceKind) {
    stopCamera();
    drafts.setKind(kind);
    clearFeedback();
  }
  function discardDraft() {
    stopCamera();
    if (source?.streamPreview && !source.saved) videoStreams.discardTemporary(source.id);
    if (source?.previewUrl?.startsWith("blob:"))
      URL.revokeObjectURL(source.previewUrl);
    drafts.discardDraft();
    clearFeedback();
  }

  async function selectFile(file: File, kind: "image" | "video") {
    const allowed =
      kind === "image"
        ? /\.(jpe?g|png|webp|gif|bmp|avif|heic|heif)$/i
        : /\.(mp4|webm|mov|m4v|ogv)$/i;
    const base: VisionSource = {
      id: crypto.randomUUID(),
      kind,
      name: file.name,
      location: file.name,
      status: "loading",
      file,
      size: file.size,
      format: file.name.split(".").pop()?.toUpperCase(),
    };
    begin(base);
    if (!allowed.test(file.name)) {
      drafts.publish({
        ...base,
        status: "error",
        error: "Định dạng tệp không phù hợp với loại source đã chọn.",
      });
      return;
    }
    if (kind === "image" && /\.(heic|heif)$/i.test(file.name)) {
      try {
        const result = await inspectImage(file);
        if (!isCurrent(base)) return;
        const previewUrl = URL.createObjectURL(result.blob);
        urls.current.add(previewUrl);
        drafts.publish({
          ...base,
          width: result.width,
          height: result.height,
          format: result.format,
          previewUrl,
          previewBlob: result.blob,
          status: "ready",
        });
      } catch (error) {
        if (isCurrent(base))
          drafts.publish({
            ...base,
            status: "error",
            error: (error as Error).message,
          });
      }
      return;
    }
    const previewUrl = URL.createObjectURL(file);
    urls.current.add(previewUrl);
    try {
      const metadata = await readMediaMetadata(previewUrl, kind);
      if (isCurrent(base))
        drafts.publish({ ...base, ...metadata, previewUrl, status: "ready" });
    } catch (error) {
      if (isCurrent(base))
        drafts.publish({
          ...base,
          status: "error",
          error: (error as Error).message,
        });
    }
  }

  async function openCamera() {
    const previous = source?.kind === "webcam" ? source : null;
    const base: VisionSource = {
      id: previous?.id ?? crypto.randomUUID(),
      kind: "webcam",
      name: previous?.name ?? "Webcam / USB",
      location: "browser-camera",
      deviceId: previous?.deviceId,
      status: "loading",
      format: "MediaStream",
    };
    begin(base);
    const request = cameraRequest.current;
    try {
      if (!navigator.mediaDevices?.getUserMedia)
        throw new Error(
          "Trình duyệt không hỗ trợ camera. Mở bằng localhost hoặc HTTPS.",
        );
      const stream = await navigator.mediaDevices.getUserMedia({
        video: base.deviceId ? { deviceId: { exact: base.deviceId } } : true,
        audio: false,
      });
      if (!isCurrent(base) || request !== cameraRequest.current) {
        stream.getTracks().forEach((track) => track.stop());
        if (isCurrent(base)) drafts.publish({ ...base, status: "pending" });
        return;
      }
      streams.current.add(stream);
      const track = stream.getVideoTracks()[0];
      const settings = track.getSettings();
      track.onended = () => {
        stopCamera();
      };
      const cameraSource: VisionSource = {
        ...base,
        name: previous?.name ?? track.label ?? base.name,
        mediaStream: stream,
        deviceId: settings.deviceId,
        width: settings.width,
        height: settings.height,
        fps: settings.frameRate,
        status: "ready",
      };
      liveCamera.current = cameraSource;
      drafts.publish(cameraSource);
    } catch (error) {
      if (isCurrent(base))
        drafts.publish({
          ...base,
          status: "error",
          error:
            error instanceof DOMException && error.name === "NotAllowedError"
              ? "Chưa được cấp quyền camera. Cho phép truy cập rồi thử lại."
              : error instanceof DOMException && error.name === "NotFoundError"
                ? "Không tìm thấy webcam/USB. Kết nối camera rồi thử lại."
                : (error as Error).message,
        });
    }
  }

  async function captureScreen() {
    const base: VisionSource = {
      id: crypto.randomUUID(),
      kind: "screen",
      name: "Ảnh màn hình",
      location: "screen-capture",
      status: "loading",
      format: "PNG",
    };
    begin(base);
    let captureStream: MediaStream | undefined;
    try {
      if (!navigator.mediaDevices?.getDisplayMedia)
        throw new Error(
          "Trình duyệt không hỗ trợ chụp màn hình. Thử Chrome trên máy tính.",
        );
      captureStream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: false,
      });
      if (!isCurrent(base)) {
        captureStream.getTracks().forEach((track) => track.stop());
        return;
      }
      streams.current.add(captureStream);
      const file = await captureScreenFrame(captureStream);
      if (!isCurrent(base)) return;
      const previewUrl = URL.createObjectURL(file);
      urls.current.add(previewUrl);
      const metadata = await readMediaMetadata(previewUrl, "image");
      if (!isCurrent(base)) return;
      drafts.publish({
        ...base,
        ...metadata,
        name: file.name,
        location: file.name,
        file,
        size: file.size,
        previewUrl,
        status: "ready",
      });
    } catch (error) {
      if (isCurrent(base))
        drafts.publish({
          ...base,
          status: "error",
          error:
            error instanceof DOMException && error.name === "NotAllowedError"
              ? "Bạn chưa chọn nội dung để chụp. Bấm chụp lại khi sẵn sàng."
              : (error as Error).message,
        });
    } finally {
      captureStream?.getTracks().forEach((track) => track.stop());
      if (captureStream) streams.current.delete(captureStream);
    }
  }

  function selectYoutube(location: string) {
    begin({
      id: crypto.randomUUID(),
      kind: "youtube",
      name: location,
      location,
      status: "pending",
      format: "YouTube",
    });
  }

  async function save(): Promise<boolean> {
    if (
      mutation.current ||
      !source ||
      !saveName.trim() ||
      !["ready", "pending"].includes(source.status)
    )
      return false;
    mutation.current = true;
    setSaving(true);
    setSaveError("");
    try {
      const saved = await saveSource(source, saveName.trim());
      savedSources.remember(saved, !source.saved);
      drafts.applySaved(source.id, saved);
      setNotice(`Đã lưu “${saved.name}”.`);
      return true;
    } catch (error) {
      setSaveError((error as Error).message);
      return false;
    } finally {
      mutation.current = false;
      setSaving(false);
    }
  }

  function updateRtspDraft(name: string, url: string) {
    drafts.setSaveName(name);
    if (url !== drafts.location) {
      if (source?.streamPreview && !source.saved) videoStreams.discardTemporary(source.id);
      drafts.setLocation(url);
    }
    clearFeedback();
  }

  async function checkRtsp(name: string, url: string): Promise<boolean> {
    const parsed = inspectRtspUrl(url);
    if (parsed.error || mutation.current) return false;
    clearFeedback();
    if (source?.streamPreview && !source.saved && drafts.location === url) {
      videoStreams.startTemporary(source.id, url);
      return true;
    }
    if (source?.streamPreview && !source.saved) videoStreams.discardTemporary(source.id);
    const address = new URL(url);
    const next: VisionSource = {
      id: crypto.randomUUID(), kind: "stream", name: name.trim() || "Camera RTSP",
      location: `${address.protocol}//${address.host}${address.pathname}`,
      status: "pending", saved: false, streamPreview: true,
      format: address.protocol.slice(0, -1).toUpperCase(),
    };
    videoStreams.startTemporary(next.id, url);
    drafts.begin(next, url);
    drafts.setSaveName(name);
    return true;
  }

  async function configureRtsp(name: string, url: string, id?: string): Promise<boolean> {
    if (mutation.current) return false;
    mutation.current = true;
    setSaving(true);
    clearFeedback();
    try {
      const saved = id && !url
        ? await renameSource(id, name)
        : await configureRtspSource(name, url, id);
      savedSources.remember(saved, !id);
      if (id) {
        drafts.applySaved(id, saved);
        if (url) videoStreams.configurationChanged(id);
      }
      else {
        if (source?.streamPreview && !source.saved) videoStreams.discardTemporary(source.id);
        drafts.begin(saved);
      }
      setNotice(`Đã lưu “${saved.name}”.`);
      return true;
    } catch (error) {
      setSaveError((error as Error).message);
      return false;
    } finally {
      mutation.current = false;
      setSaving(false);
    }
  }

  async function rename(id: string, name: string): Promise<boolean> {
    if (mutation.current) return false;
    mutation.current = true;
    setSaving(true);
    setSaveError("");
    try {
      const updated = await renameSource(id, name);
      savedSources.remember(updated);
      drafts.applySaved(id, updated);
      return true;
    } catch (error) {
      setSaveError((error as Error).message);
      return false;
    } finally {
      mutation.current = false;
      setSaving(false);
    }
  }

  async function remove(id: string): Promise<boolean> {
    if (mutation.current) return false;
    mutation.current = true;
    setSaving(true);
    setSaveError("");
    try {
      await deleteSource(id);
      videoStreams.stop(id);
      savedSources.forget(id);
      drafts.applySaved(id, null);
      clearFeedback();
      return true;
    } catch (error) {
      setSaveError((error as Error).message);
      return false;
    } finally {
      mutation.current = false;
      setSaving(false);
    }
  }

  return {
    ...drafts,
    ...savedSources,
    source,
    saveName,
    saveEnabled,
    saving,
    saveError,
    notice,
    select,
    setKind,
    setMode,
    discardDraft,
    selectFile,
    selectYoutube,
    openCamera,
    captureScreen,
    save,
    rename,
    configureRtsp,
    checkRtsp,
    updateRtspDraft,
    remove,
    stopCamera,
  };
}

export type SourceSelection = ReturnType<typeof useSourceSelectionState>;
