export async function checkLocalWebcam(deviceIndex: number) {
  const response = await fetch("/api/v1/runs/webcam/check", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ device_index: deviceIndex }),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Không kiểm tra được webcam trên máy AI.");
  return body as { device_index: number; width: number; height: number; preview_jpeg: string };
}
