import type { Metadata } from "next";
import { DatabaseWorkspace } from "@/features/database/database-workspace";

export const metadata: Metadata = { title: "Database" };

export default function DatabasePage() {
  return <DatabaseWorkspace />;
}
