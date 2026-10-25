import { DatabaseIcon, WorkflowIcon, BoxIcon } from "lucide-react";

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

export function isRouteActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}
