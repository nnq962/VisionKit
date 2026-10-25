"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { ScanEyeIcon } from "lucide-react"
import { isRouteActive, workspaceNavigation } from "@/lib/navigation"
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupLabel,
  SidebarHeader, SidebarMenu, SidebarMenuButton, SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"

export function AppSidebar(props: React.ComponentProps<typeof Sidebar>) {
  const pathname = usePathname()
  const { setOpenMobile } = useSidebar()

  return (
    <Sidebar variant="inset" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <Link href="/database" onClick={() => setOpenMobile(false)}>
                <div className="flex size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                  <ScanEyeIcon className="size-4" />
                </div>
                <div className="grid flex-1 text-left leading-tight">
                  <span className="font-semibold">VisionKit</span>
                  <span className="text-xs text-muted-foreground">Computer vision workspace</span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Workspace</SidebarGroupLabel>
          <SidebarMenu>
            {workspaceNavigation.map(({ title, href, icon: Icon }) => (
              <SidebarMenuItem key={href}>
                <SidebarMenuButton asChild isActive={isRouteActive(pathname, href)} tooltip={title}>
                  <Link href={href} onClick={() => setOpenMobile(false)} aria-current={isRouteActive(pathname, href) ? "page" : undefined}>
                    <Icon /><span>{title}</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <p className="px-2 py-2 text-xs text-muted-foreground">VisionKit · Local workspace</p>
      </SidebarFooter>
    </Sidebar>
  )
}
