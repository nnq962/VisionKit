"use client";

import { useId, useState } from "react";
import { EyeIcon, EyeOffIcon, LoaderCircleIcon, PlayIcon, SaveIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { inspectRtspUrl } from "../rtsp-configuration";

/** The stored, redacted URL is never used as an editable camera URL. */
export function RtspCameraForm({
  initialName = "", initialUrl = "", currentLocation, busy = false,
  onSave, onCancel, onDraftChange, onCheck, checking = false, canSave = false,
}: {
  initialName?: string;
  initialUrl?: string;
  currentLocation?: string;
  busy?: boolean;
  onSave: (name: string, url: string) => Promise<boolean>;
  onCheck?: (name: string, url: string) => Promise<boolean>;
  checking?: boolean;
  canSave?: boolean;
  onCancel?: () => void;
  onDraftChange?: (name: string, url: string) => void;
}) {
  const id = useId();
  const [localName, setName] = useState(initialName);
  const [localUrl, setUrl] = useState(initialUrl);
  const name = onDraftChange ? initialName : localName;
  const url = onDraftChange ? initialUrl : localUrl;
  const [visible, setVisible] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [touched, setTouched] = useState(false);
  const [savingRequested, setSavingRequested] = useState(false);
  const parsed = inspectRtspUrl(url);
  const editing = currentLocation !== undefined;
  const urlError = editing && !url.trim() ? "" : parsed.error;
  const nameError = name.trim() || (onCheck && !savingRequested) ? "" : "Đặt tên để nhận ra camera trong thư viện.";
  const showUrlError = (submitted || touched) && urlError;
  const update = (nextName: string, nextUrl: string) => {
    setName(nextName);
    setUrl(nextUrl);
    onDraftChange?.(nextName, nextUrl);
  };

  return (
    <form
      className="space-y-6"
      onSubmit={async (event) => {
        event.preventDefault();
        setSubmitted(true);
        if (busy || checking) return;
        setSavingRequested(false);
        if ((!onCheck && !name.trim()) || urlError) {
          document.getElementById(!onCheck && !name.trim() ? `${id}-name` : `${id}-url`)?.focus();
          return;
        }
        if (onCheck) await onCheck(name.trim(), url.trim());
        else await onSave(name.trim(), url.trim());
      }}
      noValidate
    >
      <div className="space-y-2">
        <Label htmlFor={`${id}-name`}>Tên camera</Label>
        <Input
          id={`${id}-name`} value={name} maxLength={120} disabled={busy}
          placeholder="Ví dụ: Camera cổng chính" autoComplete="off"
          aria-invalid={(submitted && Boolean(nameError)) || undefined}
          aria-describedby={submitted && nameError ? `${id}-name-error` : undefined}
          onChange={(event) => update(event.target.value, url)}
        />
        {onCheck && <p className="text-xs text-muted-foreground">Tuỳ chọn khi kiểm tra; cần tên nếu lưu vào thư viện.</p>}
        {submitted && nameError && <p id={`${id}-name-error`} className="text-xs text-destructive">{nameError}</p>}
      </div>
      {editing && (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">Địa chỉ hiện tại</p>
          <p className="break-all text-sm">{currentLocation}</p>
        </div>
      )}
      <div className="space-y-2">
        <Label htmlFor={`${id}-url`}>{editing ? "URL thay thế" : "URL RTSP"}</Label>
        <div className="relative">
          <Input
            id={`${id}-url`} type={visible ? "text" : "password"} value={url}
            className="pr-11" autoComplete="new-password" spellCheck={false}
            autoCapitalize="none" maxLength={2048} disabled={busy}
            placeholder={editing ? "Để trống để giữ kết nối hiện tại" : "rtsp://192.168.1.100:554/stream"}
            aria-invalid={Boolean(showUrlError) || undefined}
            aria-describedby={`${id}-url-hint${showUrlError ? ` ${id}-url-error` : ""}`}
            onBlur={() => setTouched(true)}
            onChange={(event) => update(name, event.target.value)}
          />
          <Button
            type="button" variant="ghost" size="icon-sm"
            className="absolute top-0.5 right-1" disabled={busy}
            aria-label={visible ? "Ẩn URL camera" : "Hiện URL camera"}
            aria-pressed={visible} onClick={() => setVisible(!visible)}
          >
            {visible ? <EyeOffIcon /> : <EyeIcon />}
          </Button>
        </div>
        <p id={`${id}-url-hint`} className="text-xs leading-5 text-muted-foreground">
          {editing ? "Nhập URL đầy đủ nếu đổi địa chỉ hoặc tài khoản camera." : "Dán URL từ camera. Nếu cần đăng nhập, dùng rtsp://user:password@host:port/path."}
        </p>
        {showUrlError && <p id={`${id}-url-error`} role="alert" className="text-xs text-destructive">{urlError}</p>}
      </div>
      {parsed.endpoint && (
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 border-y py-4 text-xs">
          {[
            ["Máy chủ", parsed.endpoint.host], ["Cổng", parsed.endpoint.port],
            ["Giao thức", parsed.endpoint.protocol],
            ["Tài khoản trong URL", parsed.endpoint.authenticated ? "Đã khai báo" : "Chưa khai báo"],
          ].map(([label, value]) => (
            <div key={label} className="min-w-0 space-y-1">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="break-all font-medium">{value}</dd>
            </div>
          ))}
        </dl>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={busy || checking}>
          {busy || checking ? <LoaderCircleIcon className="animate-spin motion-reduce:animate-none" /> : onCheck ? <PlayIcon /> : <SaveIcon />}
          {busy ? "Đang lưu…" : checking ? "Đang kiểm tra…" : onCheck ? "Kiểm tra và xem trực tiếp" : editing ? "Lưu cấu hình" : "Lưu và xem trực tiếp"}
        </Button>
        {onCheck && canSave && (
          <Button type="button" variant="outline" disabled={busy || checking} onClick={async () => {
            setSubmitted(true);
            setSavingRequested(true);
            if (!name.trim() || urlError) {
              document.getElementById(!name.trim() ? `${id}-name` : `${id}-url`)?.focus();
              return;
            }
            await onSave(name.trim(), url.trim());
          }}><SaveIcon /> Lưu vào thư viện</Button>
        )}
        {onCancel && <Button type="button" variant="outline" onClick={onCancel} disabled={busy}>Huỷ</Button>}
      </div>
    </form>
  );
}
