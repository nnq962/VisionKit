import type { Metadata } from "next";
import { CountingMonitorPage } from "@/features/zone-counting/counting-monitor-page";

export const metadata: Metadata = { title: "Counting Monitor" };

export default function Page() {
  return <CountingMonitorPage />;
}
