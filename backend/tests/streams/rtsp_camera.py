"""Camera RTSP H264/TCP loopback có Basic auth để smoke test relay/WebRTC."""

import asyncio
import base64
import re
import shutil
import struct


# ------------------------------ Camera kiểm thử ------------------------------
class RtspCamera:
    """Phát một IDR H264 baseline lặp 10 FPS; không dùng camera hoặc URL bên ngoài."""

    def __init__(self) -> None:
        """Khởi tạo thống kê và registry socket; chưa mở port hay encoder."""
        self.server = None
        self.writers = set()
        self.senders = set()
        self.connections = 0
        self.auth_rejections = 0
        self.nals = []
        self.port = 0
        self.sdp = b""

    async def start(self, host: str = "127.0.0.1") -> None:
        """Tạo fixture H264 bằng FFmpeg rồi tắt encoder; mở RTSP server loopback."""
        encoder = await asyncio.create_subprocess_exec(
            shutil.which("ffmpeg") or "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x180:rate=10",
            "-frames:v",
            "1",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-profile:v",
            "baseline",
            "-preset",
            "ultrafast",
            "-tune",
            "zerolatency",
            "-f",
            "h264",
            "pipe:1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        encoded, errors = await encoder.communicate()
        if encoder.returncode:
            raise RuntimeError(errors.decode())
        self.nals = [nal for nal in re.split(b"\x00\x00\x00?\x01", encoded) if nal]
        sps = next(n for n in self.nals if n[0] & 31 == 7)
        pps = next(n for n in self.nals if n[0] & 31 == 8)
        props = base64.b64encode(sps).decode() + "," + base64.b64encode(pps).decode()
        self.sdp = (
            "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=Fixture\r\nc=IN IP4 127.0.0.1\r\n"
            "t=0 0\r\na=control:*\r\nm=video 0 RTP/AVP 96\r\na=rtpmap:96 H264/90000\r\n"
            f"a=fmtp:96 packetization-mode=1;profile-level-id={sps[1:4].hex()};sprop-parameter-sets={props}\r\n"
            "a=control:trackID=0\r\n"
        ).encode()
        self.server = await asyncio.start_server(self.handle, host, 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def send(self, writer: asyncio.StreamWriter) -> None:
        """Gửi H264 bằng RTP interleaved, timestamp 90 kHz; đóng khi reader rời đi."""
        sequence, timestamp = 0, 0
        try:
            while True:
                for index, nal in enumerate(self.nals):
                    payloads = [nal]
                    if len(nal) > 1100:
                        chunks = [
                            nal[pos : pos + 1098] for pos in range(1, len(nal), 1098)
                        ]
                        payloads = [
                            bytes(
                                [
                                    (nal[0] & 0xE0) | 28,
                                    (nal[0] & 31)
                                    | (0x80 if part == 0 else 0)
                                    | (0x40 if part == len(chunks) - 1 else 0),
                                ]
                            )
                            + chunk
                            for part, chunk in enumerate(chunks)
                        ]
                    for part, payload in enumerate(payloads):
                        marker = (
                            0x80
                            if index == len(self.nals) - 1 and part == len(payloads) - 1
                            else 0
                        )
                        packet = (
                            struct.pack(
                                "!BBHII", 0x80, 96 | marker, sequence, timestamp, 1
                            )
                            + payload
                        )
                        writer.write(b"$\x00" + struct.pack("!H", len(packet)) + packet)
                        sequence = (sequence + 1) % 65536
                await writer.drain()
                timestamp = (timestamp + 9000) % (2**32)
                await asyncio.sleep(0.1)
        except (ConnectionError, asyncio.CancelledError):
            pass

    async def handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Trả SDP/SETUP/PLAY, challenge Basic user:good; chỉ lưu số lần từ chối auth."""
        self.connections += 1
        self.writers.add(writer)
        sender = None
        try:
            while True:
                first = await reader.readexactly(1)
                if first == b"$":
                    header = await reader.readexactly(3)
                    await reader.readexactly(int.from_bytes(header[1:], "big"))
                    continue
                raw = first + await reader.readuntil(b"\r\n\r\n")
                lines = raw.decode().split("\r\n")
                method = lines[0].split()[0]
                headers = {
                    k.lower(): v.strip()
                    for k, v in (
                        line.split(":", 1) for line in lines[1:] if ":" in line
                    )
                }
                length = int(headers.get("content-length", "0"))
                if length:
                    await reader.readexactly(length)
                authenticated = (
                    headers.get("authorization")
                    == "Basic " + base64.b64encode(b"user:good").decode()
                )
                if method != "OPTIONS" and not authenticated:
                    self.auth_rejections += 1
                    writer.write(
                        f'RTSP/1.0 401 Unauthorized\r\nCSeq: {headers["cseq"]}\r\nWWW-Authenticate: Basic realm="fixture"\r\nContent-Length: 0\r\n\r\n'.encode()
                    )
                    await writer.drain()
                    continue
                body, extra = b"", "Session: fixture\r\n"
                if method == "DESCRIBE":
                    body = self.sdp
                    extra += "Content-Type: application/sdp\r\n"
                elif method == "SETUP":
                    extra += "Transport: RTP/AVP/TCP;unicast;interleaved=0-1\r\n"
                elif method == "OPTIONS":
                    extra += "Public: OPTIONS, DESCRIBE, SETUP, PLAY, GET_PARAMETER, TEARDOWN\r\n"
                writer.write(
                    f"RTSP/1.0 200 OK\r\nCSeq: {headers['cseq']}\r\n{extra}Content-Length: {len(body)}\r\n\r\n".encode()
                    + body
                )
                await writer.drain()
                if method == "PLAY" and sender is None:
                    sender = asyncio.create_task(self.send(writer))
                    self.senders.add(sender)
                if method == "TEARDOWN":
                    break
        except (asyncio.IncompleteReadError, ConnectionError, asyncio.CancelledError):
            pass
        finally:
            if sender:
                sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)
                self.senders.discard(sender)
            writer.close()
            self.writers.discard(writer)

    async def close(self) -> None:
        """Dừng listener, TCP writer và RTP sender của fixture."""
        self.server.close()
        await self.server.wait_closed()
        for writer in tuple(self.writers):
            writer.close()
        for sender in tuple(self.senders):
            sender.cancel()
        await asyncio.gather(*self.senders, return_exceptions=True)
