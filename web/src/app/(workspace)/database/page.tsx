import type { Metadata } from "next";
import { SourceDatabase } from "@/features/database/source-database";

export const metadata: Metadata = { title: "Database" };

export default function DatabasePage() {
  return <SourceDatabase />;
}
