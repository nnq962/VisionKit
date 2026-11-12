import type { ReactNode } from "react";

export function WorkspacePage({
  title,
  description,
  children,
  fill = false,
  hideHeading = false,
}: {
  title: string;
  description?: string;
  fill?: boolean;
  hideHeading?: boolean;
  children: ReactNode;
}) {
  return (
    <div
      className={
        fill ? "flex h-full min-h-0 flex-col gap-4" : "flex flex-col gap-8"
      }
    >
      <div className={hideHeading ? "sr-only" : "flex shrink-0 flex-col gap-2"}>
        <h1
          className={`${fill ? "text-xl" : "text-2xl"} font-semibold tracking-tight`}
        >
          {title}
        </h1>
        {description && (
          <p className="text-sm leading-6 text-muted-foreground">
            {description}
          </p>
        )}
      </div>
      {children}
    </div>
  );
}

export function WorkspaceSection({
  title,
  titleId,
  children,
  footer,
  actions,
  stickyHeader = false,
  showHeader = true,
  toolbar,
  scrollBody = false,
  toolbarLabel = "Thanh thao tác pipeline",
  bodyLabel = "Nội dung pipeline",
  compactFooter = false,
  variant = "panel",
}: {
  title: string;
  titleId: string;
  children: ReactNode;
  footer?: ReactNode;
  actions?: ReactNode;
  stickyHeader?: boolean;
  showHeader?: boolean;
  toolbar?: ReactNode;
  scrollBody?: boolean;
  toolbarLabel?: string;
  bodyLabel?: string;
  compactFooter?: boolean;
  variant?: "panel" | "plain";
}) {
  return (
    <section
      className={
        variant === "plain"
          ? "space-y-6"
          : `${scrollBody ? "flex min-h-0 flex-1 flex-col overflow-hidden" : stickyHeader ? "overflow-visible" : "overflow-hidden"} rounded-xl border`
      }
      aria-labelledby={titleId}
    >
      {toolbar ? (
        <>
          <h2 id={titleId} tabIndex={-1} className="sr-only">
            {title}
          </h2>
          <header
            className={`${stickyHeader && !scrollBody ? "sticky top-0" : "relative"} z-20 flex shrink-0 items-start gap-3 sm:items-center ${variant === "plain" ? "border-b pb-4" : "border-b bg-muted/20 px-4 py-2 md:px-6"}`}
            aria-label={toolbarLabel}
          >
            {toolbar}
          </header>
        </>
      ) : showHeader ? (
        <div
          className={`flex flex-wrap items-center justify-between gap-3 border-b ${variant === "plain" ? "pb-4" : "p-4 md:p-6"} ${stickyHeader ? "sticky top-0 z-10 rounded-t-xl bg-background" : ""}`}
        >
          <h2
            id={titleId}
            tabIndex={-1}
            className="text-lg font-semibold outline-none"
          >
            {title}
          </h2>
          {actions && (
            <div
              className={`flex items-center justify-end ${stickyHeader || variant === "plain" ? "w-auto gap-2" : "w-full gap-3 sm:w-auto"}`}
            >
              {actions}
            </div>
          )}
        </div>
      ) : (
        <h2 id={titleId} className="sr-only">
          {title}
        </h2>
      )}
      <div
        className={
          variant === "plain"
            ? undefined
            : `${scrollBody ? "min-h-0 flex-1 overflow-y-auto overscroll-contain [scrollbar-gutter:stable]" : ""} p-4 md:p-6`
        }
        role={scrollBody ? "region" : undefined}
        aria-label={scrollBody ? bodyLabel : undefined}
        tabIndex={scrollBody ? 0 : undefined}
      >
        {children}
      </div>
      {footer && (
        <div
          className={`flex shrink-0 flex-wrap items-center justify-between gap-3 border-t ${variant === "plain" ? "pt-4" : compactFooter ? "px-4 py-2 md:px-6" : "p-4 md:p-6"}`}
        >
          {footer}
        </div>
      )}
    </section>
  );
}
