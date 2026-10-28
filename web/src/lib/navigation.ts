import { DatabaseIcon, WorkflowIcon, BoxIcon, Settings2Icon, MonitorIcon } from "lucide-react";

export const workspaceNavigation = [
  {
    title: "Database",
    href: "/database",
    icon: DatabaseIcon,
    description: "Quản lý dữ liệu",
  },
  {
    title: "Model Hub",
    href: "/models",
    icon: BoxIcon,
    description: "Khám phá và tải model",
  },
  {
    title: "YOLO pipeline",
    href: "/pipelines/yolo",
    icon: WorkflowIcon,
    description: "Thiết lập và chạy nhận diện",
  },
];

export const analyticsNavigation = [
  {
    title: "Counting Configuration",
    href: "/counting/configure",
    icon: Settings2Icon,
    description: "Configure sources, models and counting zones",
  },
  {
    title: "Counting Monitor",
    href: "/counting/monitor",
    icon: MonitorIcon,
    description: "Monitor counts and control inference",
  },
];

export const navigationGroups = [
  { title: "Workspace", items: workspaceNavigation },
  { title: "Analytics", items: analyticsNavigation },
];

export function isRouteActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}
