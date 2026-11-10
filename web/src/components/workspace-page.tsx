import type { ReactNode } from "react"

export function WorkspacePage({ title, description, children }: {
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="text-sm leading-6 text-muted-foreground">{description}</p>}
      </div>
      {children}
    </div>
  )
}

export function WorkspaceSection({ title, titleId, children, footer, actions, stickyHeader = false }: {
  title: string
  titleId: string
  children: ReactNode
  footer?: ReactNode
  actions?: ReactNode
  stickyHeader?: boolean
}) {
  return (
    <section className={`${stickyHeader ? "overflow-visible" : "overflow-hidden"} rounded-xl border`} aria-labelledby={titleId}>
      <div className={`flex flex-wrap items-center justify-between gap-3 border-b p-4 md:p-6 ${stickyHeader ? "sticky top-0 z-10 rounded-t-xl bg-background" : ""}`}>
        <h2 id={titleId} className="text-lg font-semibold">{title}</h2>
        {actions && <div className={`flex items-center justify-end ${stickyHeader ? "w-auto gap-2" : "w-full gap-3 sm:w-auto"}`}>{actions}</div>}
      </div>
      <div className="p-4 md:p-6">{children}</div>
      {footer && <div className="flex items-center justify-between gap-3 border-t p-4 md:p-6">{footer}</div>}
    </section>
  )
}
