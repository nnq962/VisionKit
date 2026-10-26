#!/usr/bin/env python3
"""Khởi chạy VisionKit local, kiểm tra sẵn sàng và thu hồi đúng các process đã tạo."""

import argparse
import fcntl
import json
import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def choose_port(preferred: int, explicit: int | None, reserved: set[int]) -> int:
    """Chọn cổng loopback còn trống; cổng chỉ định rõ phải khả dụng."""
    candidates = (
        [explicit] if explicit is not None else range(preferred, preferred + 100)
    )
    for port in candidates:
        if port in reserved:
            continue
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
        reserved.add(port)
        return port
    raise RuntimeError(
        f"Cổng {explicit or preferred} đang bận hoặc không khả dụng. Chọn cổng khác bằng --*-port."
    )


def web_is_running() -> bool:
    """Nhận biết Next.js đang chạy trước khi backend đụng DB dùng chung."""
    try:
        value = json.loads((ROOT / "web/.next/dev/lock").read_text())
        pid = value.get("pid") if isinstance(value, dict) else None
        if not isinstance(pid, int) or pid <= 0:
            return False
        os.kill(pid, 0)
        proc = Path(f"/proc/{pid}/cwd")
        return proc.resolve() == ROOT / "web" if Path("/proc").is_dir() else True
    except (OSError, ValueError):
        return False


def stop_session(data: Path) -> int:
    """Dừng launcher đang giữ lock của thư mục dữ liệu; từ chối PID không đúng script."""
    path = data / "dev-logs/session.lock"
    if not path.exists():
        print("Không có phiên launcher đang chạy.")
        return 0
    with path.open("r+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            print("Không có phiên launcher đang chạy.")
            return 0
        pid = int(lock.read().strip())
        if pid <= 1:
            raise RuntimeError("PID launcher không hợp lệ.")
        if Path("/proc").is_dir():
            args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            cwd = Path(f"/proc/{pid}/cwd").resolve()
            owned = any(
                (cwd / os.fsdecode(arg)).resolve() == ROOT / "dev.py"
                for arg in args
                if arg
            )
        else:
            command = subprocess.run(
                ["ps", "-p", str(pid), "-o", "command="],
                capture_output=True,
                text=True,
                check=False,
            )
            owned = "dev.py" in command.stdout
        if not owned:
            raise RuntimeError(
                "PID trong session.lock không thuộc launcher này; không gửi tín hiệu."
            )
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                time.sleep(0.1)
            else:
                print("Đã dừng phiên VisionKit và các dịch vụ con.")
                return 0
        raise RuntimeError(
            "Launcher chưa dừng sau 15 giây; kiểm tra log trước khi thử lại."
        )


def healthy(url: str, *, ai: bool = False) -> bool:
    """Xác nhận phản hồi API thay vì chỉ kiểm tra socket đã mở."""
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            body = json.load(response)
        return (
            body.get("ai", {}).get("available") is True
            if ai
            else body.get("status") == "ok"
        )
    except (OSError, ValueError, urllib.error.URLError):
        return False


class Service:
    """Giữ process group và luồng đọc log hữu hạn của một dịch vụ con."""

    def __init__(
        self,
        name: str,
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        log_dir: Path,
    ) -> None:
        """Mở log xoay vòng và process group riêng; không nhận quyền quản lý process cũ."""
        self.name = name
        self.path = log_dir / f"{name}.log"
        self.handler = RotatingFileHandler(
            self.path, maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8"
        )
        self.handler.setFormatter(logging.Formatter("%(message)s"))
        self.read_error: Exception | None = None
        try:
            self.process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except BaseException:
            self.handler.close()
            raise
        self.thread = threading.Thread(
            target=self.drain, name=f"log-{name}", daemon=True
        )
        self.thread.start()
        print(f"[{name}] PID {self.process.pid} · log: {self.path}", flush=True)

    def drain(self) -> None:
        """Rút pipe liên tục theo dòng tối đa 8 KiB, không giữ hàng đợi log trong RAM."""
        try:
            assert self.process.stdout is not None
            with self.process.stdout as stream:
                while chunk := stream.readline(8192):
                    self.handler.emit(
                        logging.LogRecord(
                            self.name,
                            logging.INFO,
                            "",
                            0,
                            chunk.decode("utf-8", errors="replace").rstrip("\n"),
                            (),
                            None,
                        )
                    )
        except (OSError, ValueError) as error:
            self.read_error = error

    def check(self) -> None:
        """Báo lỗi nếu dịch vụ hoặc bộ đọc pipe đã dừng."""
        if self.read_error:
            raise RuntimeError(f"Không đọc được log {self.name}: {self.read_error}")
        code = self.process.poll()
        if code is not None:
            try:
                with self.path.open(encoding="utf-8") as log:
                    tail = "".join(deque(log, maxlen=12))
            except OSError:
                tail = ""
            raise RuntimeError(f"{self.name} đã dừng (mã {code}).\n{tail}")


def shutdown(services: list[Service]) -> None:
    """Dừng toàn bộ group sở hữu, bao gồm Next.js và worker inference, rồi đóng log."""
    for child in reversed(services):
        try:
            os.killpg(child.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 8
    for child in reversed(services):
        try:
            child.process.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
    for child in reversed(services):
        # Parent npm có thể đã thoát trước Next.js; vẫn thu hồi group đã tạo.
        try:
            os.killpg(child.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.process.wait()
        child.thread.join(timeout=3)
        child.handler.close()


def wait_ready(
    services: list[Service],
    url: str,
    name: str,
    stopping: threading.Event,
    *,
    ai: bool = False,
) -> None:
    """Đợi readiness có timeout; kiểm tra mọi process để báo lỗi startup sớm."""
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if stopping.is_set():
            raise KeyboardInterrupt
        for child in services:
            child.check()
        if healthy(url, ai=ai):
            print(f"[ok] {name}", flush=True)
            return
        stopping.wait(0.25)
    raise RuntimeError(
        f"Hết thời gian chờ {name}. Kiểm tra log trong thư mục đã in ở trên."
    )


def main() -> int:
    """Chạy cả ba dịch vụ, trả mã lỗi nếu một dịch vụ dừng; Ctrl+C dọn tài nguyên."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Dừng phiên launcher của thư mục dữ liệu này.",
    )
    parser.add_argument("--backend-port", type=int)
    parser.add_argument("--ai-port", type=int)
    parser.add_argument("--web-port", type=int)
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Thư mục DB/file riêng; mặc định dùng cấu hình hiện có.",
    )
    parser.add_argument(
        "--no-web",
        action="store_true",
        help="Chỉ chạy backend và AI (cho kiểm thử/API).",
    )
    args = parser.parse_args()
    for port in (args.backend_port, args.ai_port, args.web_port):
        if port is not None and not 1024 <= port <= 65535:
            parser.error("Cổng phải nằm trong khoảng 1024–65535.")
    if os.name != "posix":
        parser.error("Script này dùng process group POSIX (Linux/macOS).")
    services: list[Service] = []
    session_lock = None
    stopping = threading.Event()

    def stop(signum: int, frame: object) -> None:
        """Chuyển tín hiệu dừng thành luồng cleanup, tránh khởi chạy thêm dịch vụ."""
        stopping.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        if args.stop:
            data = (
                args.data_dir.expanduser().resolve() if args.data_dir else ROOT / "data"
            )
            return stop_session(data)
        for module in ("ai", "backend"):
            if not (ROOT / module / ".venv/bin/python").is_file():
                raise RuntimeError(
                    f"Thiếu môi trường {module}. Chạy: cd {module} && uv sync"
                )
        if not args.no_web and (
            not shutil.which("npm") or not (ROOT / "web/node_modules/next").is_dir()
        ):
            raise RuntimeError("Thiếu npm/dependency web. Chạy: cd web && npm install")
        if not args.no_web and web_is_running():
            raise RuntimeError(
                "Next.js development đã chạy trong project. Dừng phiên dev cũ trước khi bật một phiên mới."
            )
        reserved: set[int] = set()
        # Ưu tiên mọi cổng được chỉ định trước khi tự chọn cổng còn lại.
        chosen = {
            name: choose_port(value, value, reserved)
            for name, value in (
                ("ai", args.ai_port),
                ("backend", args.backend_port),
                ("web", args.web_port),
            )
            if value is not None and (name != "web" or not args.no_web)
        }
        for name, preferred in (("ai", 8001), ("backend", 8000), ("web", 3001)):
            if name not in chosen and (name != "web" or not args.no_web):
                chosen[name] = choose_port(preferred, None, reserved)
        env = dict(os.environ)
        env["VISIONKIT_AI_URL"] = f"http://127.0.0.1:{chosen['ai']}"
        env["VISIONKIT_API_URL"] = f"http://127.0.0.1:{chosen['backend']}"
        if not args.no_web:
            origins = env.get(
                "VISIONKIT_CORS_ORIGINS", "http://localhost:3001,http://localhost:3000"
            )
            env["VISIONKIT_CORS_ORIGINS"] = (
                origins
                + f",http://127.0.0.1:{chosen['web']},http://localhost:{chosen['web']}"
            )
        data = args.data_dir.expanduser().resolve() if args.data_dir else ROOT / "data"
        if args.data_dir:
            for key, path in {
                "DB_PATH": data / "visionkit.sqlite3",
                "SOURCES_PATH": data / "sources",
                "MODELS_PATH": data / "models",
                "RUNS_PATH": data / "runs",
            }.items():
                env[f"VISIONKIT_{key}"] = str(path)
        log_dir = data / "dev-logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        session_lock = (log_dir / "session.lock").open("a+")
        try:
            fcntl.flock(session_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(
                "Đã có một launcher dùng thư mục dữ liệu này; dừng phiên cũ trước."
            ) from error
        session_lock.seek(0)
        session_lock.truncate()
        session_lock.write(f"{os.getpid()}\n")
        session_lock.flush()
        for name, module in (("ai", "ai"), ("backend", "backend")):
            services.append(
                Service(
                    name,
                    [
                        str(ROOT / module / ".venv/bin/python"),
                        "-m",
                        "uvicorn",
                        "app.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(chosen[name]),
                    ],
                    ROOT / module,
                    env,
                    log_dir,
                )
            )
            wait_ready(
                services,
                f"http://127.0.0.1:{chosen[name]}/api/v1/health",
                f"{name} sẵn sàng",
                stopping,
            )
        wait_ready(
            services,
            f"{env['VISIONKIT_API_URL']}/api/v1/logs?limit=1",
            "Backend kết nối được AI",
            stopping,
            ai=True,
        )
        if not args.no_web:
            services.append(
                Service(
                    "web",
                    [
                        "npm",
                        "run",
                        "dev",
                        "--",
                        "--hostname",
                        "127.0.0.1",
                        "--port",
                        str(chosen["web"]),
                    ],
                    ROOT / "web",
                    env,
                    log_dir,
                )
            )
            wait_ready(
                services,
                f"http://127.0.0.1:{chosen['web']}/api/v1/health",
                "Proxy frontend kết nối được backend",
                stopping,
            )
            print(f"\nFrontend: http://127.0.0.1:{chosen['web']}\n", flush=True)
        print(
            f"Backend: {env['VISIONKIT_API_URL']}/docs\nAI: {env['VISIONKIT_AI_URL']}\nCtrl+C để dừng tất cả dịch vụ của phiên này.",
            flush=True,
        )
        while not stopping.is_set():
            for child in services:
                child.check()
            stopping.wait(0.5)
        raise KeyboardInterrupt
    except KeyboardInterrupt:
        print("\nĐang dừng các dịch vụ…", flush=True)
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Lỗi: {error}", file=sys.stderr, flush=True)
        return 1
    finally:
        shutdown(services)
        if session_lock is not None:
            session_lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
