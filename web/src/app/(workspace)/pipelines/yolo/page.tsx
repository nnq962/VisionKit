import type { Metadata } from "next"
import { YoloPipeline } from "@/features/pipelines/yolo/yolo-pipeline"

export const metadata: Metadata = { title: "YOLO pipeline" }

export default function YoloPage() {
  return <YoloPipeline />
}
