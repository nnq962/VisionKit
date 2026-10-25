export async function captureScreenFrame(stream: MediaStream): Promise<File> {
  const video = document.createElement("video");
  video.muted = true;
  video.srcObject = stream;
  try {
    await new Promise<void>((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        cleanup();
        reject(new Error("Không đọc được hình từ màn hình. Thử chụp lại."));
      }, 8000);
      function cleanup() {
        clearTimeout(timeout);
        video.onloadeddata = null;
        video.onerror = null;
      }
      video.onloadeddata = () => {
        cleanup();
        resolve();
      };
      video.onerror = () => {
        cleanup();
        reject(new Error("Không đọc được hình từ màn hình."));
      };
      void video.play().catch((error) => {
        cleanup();
        reject(error);
      });
    });
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");
    if (!context || !canvas.width || !canvas.height)
      throw new Error("Không chụp được ảnh. Thử lại.");
    context.drawImage(video, 0, 0);
    const blob = await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob(
        (value) =>
          value ? resolve(value) : reject(new Error("Không tạo được ảnh.")),
        "image/png",
      ),
    );
    return new File([blob], `screenshot-${Date.now()}.png`, {
      type: "image/png",
    });
  } finally {
    stream.getTracks().forEach((track) => track.stop());
    video.srcObject = null;
  }
}
