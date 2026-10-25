import type { Metadata } from "next";
import { ModelHub } from "@/features/models/model-hub";

export const metadata: Metadata = { title: "Model Hub" };

export default function ModelsPage() {
  return <ModelHub />;
}
