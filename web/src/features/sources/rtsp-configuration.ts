/** Validate camera URLs without including credentials in feedback or summaries. */
export function inspectRtspUrl(value: string) {
  const raw = value.trim();
  if (!raw) return { error: "Nhập địa chỉ RTSP của camera.", endpoint: null };
  if (raw.length > 2048) return { error: "Địa chỉ tối đa 2.048 ký tự.", endpoint: null };
  if (/[\s\x00-\x1f\x7f]/.test(raw)) {
    return { error: "Địa chỉ không được chứa khoảng trắng hoặc xuống dòng.", endpoint: null };
  }
  try {
    const url = new URL(raw);
    if (!["rtsp:", "rtsps:"].includes(url.protocol) || !url.hostname || url.hash) {
      throw new Error();
    }
    if (url.port && (!/^\d+$/.test(url.port) || Number(url.port) < 1 || Number(url.port) > 65535)) {
      throw new Error();
    }
    return {
      error: "",
      endpoint: {
        protocol: url.protocol.slice(0, -1).toUpperCase(),
        host: url.hostname,
        port: url.port || (url.protocol === "rtsps:" ? "322" : "554"),
        authenticated: Boolean(url.username || url.password),
      },
    };
  } catch {
    return { error: "Dùng URL rtsp:// hoặc rtsps:// có địa chỉ camera và cổng hợp lệ.", endpoint: null };
  }
}
