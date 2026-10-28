import type { Metadata } from "next";
import { CountingPage } from "@/features/zone-counting/counting-page";

export const metadata: Metadata = { title: "Counting Configuration" };

export default function Page() {
  return <CountingPage configureOnly />;
}
