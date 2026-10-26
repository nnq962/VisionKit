"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Dialog } from "radix-ui";
import {
  ArrowDownToLineIcon, CheckIcon, ChevronRightIcon, CircleAlertIcon,
  GripVerticalIcon, Maximize2Icon, Minimize2Icon, PauseIcon, PlayIcon, SearchIcon,
  TerminalIcon, Trash2Icon, XIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

import { useFloatingWindow } from "./use-floating-window";

import type { LogLevel } from "./log-stream";
import { useRuntimeLogs } from "./use-runtime-logs";

const LEVEL_STYLE: Record<LogLevel, string> = {
  DEBUG: "text-slate-400",
  INFO: "text-sky-300",
  WARNING: "text-amber-300",
  ERROR: "text-rose-300",
  CRITICAL: "text-rose-300",
};

const RESIZE_HANDLES = [
  { direction: "n", label: "cạnh trên", className: "inset-x-3 top-0 h-1.5 cursor-ns-resize" },
  { direction: "s", label: "cạnh dưới", className: "inset-x-3 bottom-0 h-1.5 cursor-ns-resize" },
  { direction: "e", label: "cạnh phải", className: "inset-y-3 right-0 w-1.5 cursor-ew-resize" },
  { direction: "w", label: "cạnh trái", className: "inset-y-3 left-0 w-1.5 cursor-ew-resize" },
  { direction: "ne", label: "góc trên phải", className: "top-0 right-0 size-4 cursor-nesw-resize" },
  { direction: "nw", label: "góc trên trái", className: "top-0 left-0 size-4 cursor-nwse-resize" },
  { direction: "se", label: "góc dưới phải", className: "right-0 bottom-0 size-4 cursor-nwse-resize" },
  { direction: "sw", label: "góc dưới trái", className: "bottom-0 left-0 size-4 cursor-nesw-resize" },
] as const;

export function LogViewer() {
  const [open, setOpen] = useState(false);
  const { windowRef, style: windowStyle, headerProps, expanded, toggleExpanded, getResizeHandleProps } = useFloatingWindow(open);
  const [paused, setPaused] = useState(false);
  const [following, setFollowing] = useState(true);
  const [service, setService] = useState("all");
  const [level, setLevel] = useState("all");
  const [search, setSearch] = useState("");
  const { entries, ai, connection, notice, clear, dismissNotice } = useRuntimeLogs(open, paused);
  const viewport = useRef<HTMLDivElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);

  const query = search.trim().toLocaleLowerCase();
  const filtered = useMemo(() => entries.filter((entry) =>
    (service === "all" || entry.service === service) &&
    (level === "all" || entry.level === level || (level === "ERROR" && entry.level === "CRITICAL")) &&
    (!query || `${entry.message} ${entry.traceback ?? ""} ${entry.service} ${entry.logger} ${entry.run_id ?? ""}`.toLocaleLowerCase().includes(query)),
  ), [entries, service, level, query]);
  const errors = filtered.filter((entry) => (entry.level === "ERROR" || entry.level === "CRITICAL")).length;
  const warnings = filtered.filter((entry) => entry.level === "WARNING").length;

  const rows = useMemo(() => filtered.map((entry) => (
              <div key={entry.id} className={`-mx-3 border-l-2 px-3 py-1 @sm:-mx-4 @sm:px-4 ${(entry.level === "ERROR" || entry.level === "CRITICAL") ? "border-rose-400/70 bg-rose-400/7" : entry.level === "WARNING" ? "border-amber-300/60 bg-amber-300/4" : "border-transparent"}`}>
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0 @sm:flex-nowrap @sm:gap-x-3">
                  <time dateTime={entry.timestamp} title={new Date(entry.timestamp).toLocaleString("vi-VN")} className="shrink-0 text-slate-500">{new Date(entry.timestamp).toLocaleTimeString("vi-VN", { hour12: false })}</time>
                  <span className={`w-14 shrink-0 text-[10px] font-semibold ${LEVEL_STYLE[entry.level]}`}>{entry.level === "WARNING" ? "WARN" : entry.level}</span>
                  <span className={`w-13 shrink-0 text-[10px] ${entry.service === "ai" ? "text-violet-300" : "text-slate-400"}`}>{entry.service === "ai" ? "ai" : "backend"}</span>
                  <span title={[entry.logger, entry.run_id && `Run: ${entry.run_id}`].filter(Boolean).join(" · ")} className={`min-w-0 basis-full whitespace-pre-wrap break-words [overflow-wrap:anywhere] @sm:basis-auto ${(entry.level === "ERROR" || entry.level === "CRITICAL") ? "text-rose-200" : ""}`}>{entry.message}</span>
                </div>
                {entry.traceback && <details className="mt-1 @sm:ml-[214px]">
                  <summary className="flex w-fit cursor-pointer list-none items-center gap-1 rounded text-[10px] text-rose-300 hover:text-rose-200 focus-visible:outline-2 focus-visible:outline-rose-300 [&::-webkit-details-marker]:hidden"><ChevronRightIcon className="size-3 in-details-open:rotate-90" />Chi tiết lỗi</summary>
                  <pre className="mt-2 overflow-x-auto rounded-md border border-rose-300/15 bg-black/20 p-2.5 text-[10px] leading-relaxed text-rose-200/80">{entry.traceback}</pre>
                </details>}
              </div>
            )), [filtered]);

  useEffect(() => {
    if (open && following && viewport.current) {
      viewport.current.scrollTop = viewport.current.scrollHeight;
    }
  }, [open, following, entries, service, level, search]);

  return (
    <Dialog.Root open={open} onOpenChange={setOpen} modal={false}>
      <Dialog.Trigger asChild>
        <Button variant={open ? "secondary" : "ghost"} className="gap-2" aria-label="Mở cửa sổ log">
          <TerminalIcon />
          <span>Log</span>
        </Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Content
          ref={windowRef}
          style={windowStyle}
          aria-describedby="log-preview-description"
          onOpenAutoFocus={(event) => { event.preventDefault(); closeButton.current?.focus(); }}
          onInteractOutside={(event) => event.preventDefault()}
          className={`@container fixed right-3 bottom-3 z-40 flex max-h-[calc(100dvh-24px)] max-w-[calc(100vw-24px)] w-[calc(100vw-24px)] flex-col overflow-hidden rounded-xl border bg-background text-foreground shadow-[0_16px_64px_-12px_rgba(15,23,42,0.32)] outline-none data-[state=open]:animate-in data-[state=open]:fade-in-0 motion-reduce:animate-none sm:right-6 sm:bottom-6 ${expanded ? "h-[680px] sm:w-[min(900px,calc(100vw-48px))]" : "h-[470px] sm:w-[min(640px,calc(100vw-24px))]"}`}
        >
          <div
            {...headerProps}
            tabIndex={0}
            role="group"
            aria-label="Di chuyển cửa sổ log"
            aria-describedby="log-drag-hint"
            title="Kéo để di chuyển cửa sổ log"
            className="flex shrink-0 touch-none cursor-grab select-none items-center gap-3 border-b px-4 py-3 outline-none data-[dragging=true]:cursor-grabbing focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
          >
            <span id="log-drag-hint" className="sr-only">Kéo header hoặc dùng phím mũi tên để di chuyển. Giữ Shift để di chuyển nhanh. Nhấn Home để về vị trí mặc định.</span>
            <GripVerticalIcon aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground/60" />
            <div className="hidden size-9 shrink-0 items-center justify-center rounded-lg border bg-muted/60 text-primary @sm:flex"><TerminalIcon className="size-4" /></div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <Dialog.Title className="truncate text-sm font-semibold">Nhật ký hệ thống</Dialog.Title>
                <span className="hidden shrink-0 rounded border bg-muted/60 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground @sm:inline">Trực tiếp</span>
              </div>
              <Dialog.Description id="log-preview-description" className="mt-0.5 truncate text-xs text-muted-foreground">Backend & AI engine</Dialog.Description>
            </div>
            <Button size="icon-sm" variant="ghost" aria-label={expanded ? "Thu gọn cửa sổ log" : "Mở rộng cửa sổ log"} title={expanded ? "Thu gọn" : "Mở rộng"} onClick={toggleExpanded}>
              {expanded ? <Minimize2Icon /> : <Maximize2Icon />}
            </Button>
            <Dialog.Close asChild>
              <Button ref={closeButton} size="icon-sm" variant="ghost" aria-label="Đóng cửa sổ log" title="Đóng"><XIcon /></Button>
            </Dialog.Close>
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-2 px-4 pt-3 pb-2">
            <div className="flex w-full rounded-lg bg-muted p-0.5 @sm:w-auto" role="group" aria-label="Lọc nguồn log">
              {[["all", "Tất cả"], ["backend", "Backend"], ["ai", "AI engine"]].map(([value, label]) => (
                <button key={value} type="button" aria-pressed={service === value} onClick={() => setService(value)} className={`flex-1 whitespace-nowrap rounded-md px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-ring ${service === value ? "bg-background text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"}`}>{label}</button>
              ))}
            </div>
            <Select value={level} onValueChange={setLevel}>
              <SelectTrigger size="sm" aria-label="Lọc mức độ log" className="border-border text-xs"><SelectValue /></SelectTrigger>
              <SelectContent position="popper"><SelectGroup>
                <SelectItem value="all">Mọi mức độ</SelectItem>
                <SelectItem value="DEBUG">Debug</SelectItem>
                <SelectItem value="INFO">Thông tin</SelectItem>
                <SelectItem value="WARNING">Cảnh báo</SelectItem>
                <SelectItem value="ERROR">Lỗi</SelectItem>
              </SelectGroup></SelectContent>
            </Select>
            <div className="ml-auto flex gap-1">
              <Button size="icon-sm" variant="ghost" aria-label={paused ? "Tiếp tục nhận log" : "Tạm dừng nhận log"} title={paused ? "Tiếp tục" : "Tạm dừng"} aria-pressed={paused} onClick={() => setPaused(!paused)}>{paused ? <PlayIcon /> : <PauseIcon />}</Button>
              <Button size="icon-sm" variant="ghost" aria-label="Xóa log đang hiển thị" title="Xóa màn hình" disabled={!entries.length} onClick={clear}><Trash2Icon /></Button>
            </div>
          </div>
          <div className="relative mx-4 mb-3 shrink-0">
            <SearchIcon aria-hidden="true" className="absolute top-2 left-2.5 size-3.5 text-muted-foreground" />
            <input value={search} onChange={(event) => setSearch(event.target.value)} aria-label="Tìm trong log" placeholder="Tìm trong log…" className="h-8 w-full rounded-lg border border-border bg-muted/30 pr-8 pl-8 text-xs outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/20" />
            {search && <button type="button" aria-label="Xóa tìm kiếm log" onClick={() => setSearch("")} className="absolute top-1.5 right-2 rounded p-0.5 text-muted-foreground"><XIcon className="size-3.5" /></button>}
          </div>

          {(notice || connection === "offline" || (ai && (!ai.configured || ai.available === false))) && (
            <div role="status" className="flex shrink-0 items-start gap-2 border-t bg-muted/50 px-4 py-2 text-xs text-muted-foreground">
              <CircleAlertIcon className="mt-0.5 size-3.5 shrink-0 text-warning" />
              <div className="min-w-0 flex-1 space-y-1">
                {connection === "offline" && <p>{paused ? "Mất kết nối backend. Tiếp tục để kết nối lại." : "Mất kết nối backend. Đang tự thử lại; log đã tải vẫn được giữ."}</p>}
                {ai && (!ai.configured || ai.available === false) && <p>{!ai.configured ? "AI chưa được cấu hình." : "Không lấy được log AI. Log backend vẫn được cập nhật."}</p>}
                {notice && <p>{notice}</p>}
              </div>
              {notice && <button type="button" aria-label="Đóng thông báo lịch sử log" onClick={dismissNotice} className="rounded p-0.5"><XIcon className="size-3.5" /></button>}
            </div>
          )}

          <div ref={viewport} tabIndex={0} role="region" aria-label="Nội dung log hệ thống" onScroll={(event) => { const target = event.currentTarget; setFollowing(target.scrollHeight - target.scrollTop - target.clientHeight < 24); }} className="min-h-0 flex-1 overflow-auto overscroll-contain bg-[#151923] px-3 py-2 font-mono text-[11px] leading-5 text-slate-300 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary @sm:px-4">
            {filtered.length ? rows : <div className="flex h-full min-h-28 flex-col items-center justify-center gap-2 text-slate-400"><SearchIcon className="size-5 text-slate-500" /><p>{entries.length ? "Không tìm thấy log phù hợp." : paused ? "Đã tạm dừng nhận log." : connection === "connecting" ? "Đang tải log…" : connection === "offline" ? "Chưa kết nối được backend." : "Chưa có log để hiển thị."}</p><span className="text-[10px] text-slate-500">{entries.length ? "Thử thay đổi bộ lọc hoặc từ khóa." : paused ? "Tiếp tục để nhận log mới." : connection === "offline" ? "Đang tự động thử kết nối lại." : "Log mới sẽ tự động xuất hiện tại đây."}</span></div>}
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-3 border-t px-4 py-2 text-[10px] text-muted-foreground">
            <span className="flex items-center gap-1.5"><span className={`size-1.5 rounded-full ${paused ? "bg-amber-500" : connection === "online" ? "bg-emerald-500" : connection === "offline" ? "bg-rose-500" : "bg-slate-400"}`} />{paused ? "Đã tạm dừng" : connection === "online" ? "Đang theo dõi" : connection === "offline" ? "Đang kết nối lại" : "Đang kết nối"}</span>
            <span title="Giữ tối đa 2.000 dòng gần nhất">{filtered.length} dòng</span>
            <span className="hidden @sm:inline" title={ai?.last_success_at ? `Lần thu AI gần nhất: ${new Date(ai.last_success_at).toLocaleString("vi-VN")}` : undefined}>AI: {!ai ? "Đang kiểm tra" : !ai.configured ? "Chưa cấu hình" : ai.available === null ? "Đang kiểm tra" : ai.available ? "Đã kết nối" : "Mất kết nối"}</span>
            {(errors > 0 || warnings > 0) && <span className="hidden items-center gap-2 @sm:flex">{errors > 0 && <span className="flex items-center gap-1 text-destructive"><CircleAlertIcon className="size-3" />{errors} lỗi</span>}{warnings > 0 && <span className="text-warning">{warnings} cảnh báo</span>}</span>}
            <button type="button" aria-pressed={following} onClick={() => setFollowing(!following)} className={`ml-auto flex items-center gap-1.5 rounded py-1 font-medium focus-visible:outline-2 focus-visible:outline-ring ${following ? "text-primary" : "text-muted-foreground hover:text-foreground"}`}>{following ? <CheckIcon className="size-3" /> : <ArrowDownToLineIcon className="size-3" />}Theo dõi cuối</button>
          </div>
          <span id="log-resize-hint" className="sr-only">Kéo cạnh hoặc góc để đổi kích thước. Tại góc dưới phải, dùng phím mũi tên; giữ Shift để thay đổi nhanh hơn.</span>
          {RESIZE_HANDLES.map(({ direction, label, className }) => (
            <div key={direction} {...getResizeHandleProps(direction)}
              role="group" aria-describedby="log-resize-hint" aria-label={`Đổi kích thước cửa sổ log: ${label}`} title={`Kéo để đổi kích thước (${label})`}
              tabIndex={direction === "se" ? 0 : -1}
              className={`absolute z-10 touch-none select-none focus-visible:outline-2 focus-visible:outline-ring ${className}`}>
              {direction === "se" && <svg aria-hidden="true" viewBox="0 0 12 12" className="absolute right-1 bottom-1 size-2.5 text-muted-foreground/60"><path d="M3 10 10 3M7 10l3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>}
            </div>
          ))}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
