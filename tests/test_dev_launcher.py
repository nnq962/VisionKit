"""Kiểm tra launcher bằng ba process thật và API/frontend fixture, không chạy AI."""

import hashlib
import importlib.util
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("visionkit_dev", ROOT / "dev.py")
DEV = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEV)

API = """import json, os, urllib.request
async def app(scope, receive, send):
    if scope['type'] == 'lifespan':
        while True:
            message = await receive()
            if message['type'] == 'lifespan.startup':
                await send({'type':'lifespan.startup.complete'})
            elif message['type'] == 'lifespan.shutdown':
                await send({'type':'lifespan.shutdown.complete'})
                return
    else:
        if scope['path'].endswith('/logs'):
            with urllib.request.urlopen(os.environ['VISIONKIT_AI_URL']+'/api/v1/health') as response:
                ok = json.load(response)['status'] == 'ok'
            body = {'ai':{'available':ok}}
        else:
            body = {'status':'ok'}
        await send({'type':'http.response.start','status':200,'headers':[(b'content-type',b'application/json')]})
        await send({'type':'http.response.body','body':json.dumps(body).encode()})
"""
WEB = """import http from 'node:http';
const port = Number(process.argv[process.argv.indexOf('--port') + 1]);
http.createServer(async (_req, res) => {
  try {
    const reply = await fetch(process.env.VISIONKIT_API_URL + '/api/v1/health');
    res.writeHead(reply.status, {'Content-Type':'application/json'});
    res.end(await reply.text());
  } catch { res.writeHead(502); res.end('{}'); }
}).listen(port, '127.0.0.1');
"""


def free_port() -> int:
    """Lấy một cổng tạm để kiểm thử mà không thay đổi dịch vụ đang có."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class PortTests(unittest.TestCase):
    """Không chiếm cổng bận; cho phép restart trên cổng có kết nối TIME_WAIT."""

    def test_occupied_port_and_auto_selection(self) -> None:
        """Cổng explicit đang nghe bị từ chối; chế độ auto chọn cổng kế tiếp."""
        with socket.socket() as busy:
            busy.bind(("127.0.0.1", 0))
            busy.listen()
            port = busy.getsockname()[1]
            with self.assertRaises(RuntimeError):
                DEV.choose_port(port, port, set())
            self.assertNotEqual(DEV.choose_port(port, None, set()), port)

    def test_explicit_conflict_does_not_start_children(self) -> None:
        """Cấu hình trùng cổng thất bại trước khi mở bất kỳ dịch vụ nào."""
        port = free_port()
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "dev.py"),
                "--no-web",
                "--ai-port",
                str(port),
                "--backend-port",
                str(port),
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("PID", result.stdout)


@unittest.skipUnless(
    shutil.which("npm") and (ROOT / "backend/.venv/bin/python").exists(),
    "Cần npm và môi trường backend",
)
class LauncherLifecycleTests(unittest.TestCase):
    """Chạy ba process, kiểm tra proxy, tín hiệu dừng và cleanup khi một service lỗi."""

    def setUp(self) -> None:
        """Tạo project fixture riêng; không đụng DB, web dev lock hay process người dùng."""
        self.directory = tempfile.TemporaryDirectory(prefix="visionkit-launcher-test-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        shutil.copyfile(ROOT / "dev.py", self.root / "dev.py")
        for name in ("ai", "backend"):
            module = self.root / name
            (module / "app").mkdir(parents=True)
            (module / "app/__init__.py").touch()
            (module / "app/main.py").write_text(API)
            (module / ".venv").symlink_to(
                ROOT / "backend/.venv", target_is_directory=True
            )
        (self.root / "web/node_modules/next").mkdir(parents=True)
        (self.root / "web/package.json").write_text(
            json.dumps({"type": "module", "scripts": {"dev": "node server.mjs"}})
        )
        (self.root / "web/server.mjs").write_text(WEB)
        self.ports = {name: free_port() for name in ("ai", "backend", "web")}
        while len(set(self.ports.values())) < 3:
            self.ports = {name: free_port() for name in ("ai", "backend", "web")}
        self.output = self.root / "launcher.log"
        self.process = None
        self.addCleanup(self.stop)

    def stop(self) -> None:
        """Yêu cầu launcher đóng các process con trước khi dọn thư mục fixture."""
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=15)

    def start(self, *, media: bool = False, supervise: bool = False) -> None:
        """Khởi chạy launcher fixture và đợi thông báo readiness có giới hạn."""
        command = [sys.executable, str(self.root / "dev.py")]
        if supervise:
            command.append("--supervise")
        if not media:
            command.append("--no-media")
        for name, port in self.ports.items():
            command.extend([f"--{name}-port", str(port)])
        with self.output.open("w") as output:
            self.process = subprocess.Popen(
                command, stdout=output, stderr=subprocess.STDOUT
            )
        for _ in range(150):
            text = self.output.read_text()
            if "Ctrl+C" in text or self.process.poll() is not None:
                return
            time.sleep(0.1)
        self.fail(self.output.read_text())

    def assert_ports_released(self) -> None:
        """Sau cleanup, cả ba cổng phải bind lại được."""
        for port in self.ports.values():
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(("127.0.0.1", port))

    @unittest.skipUnless(
        os.getenv("VISIONKIT_RUN_DOCKER_TESTS") == "1" and shutil.which("docker"),
        "Cần bật integration Docker",
    )
    def test_media_relay_startup_and_cleanup(self) -> None:
        """Launcher mở relay thật trước backend và thu hồi process khi kết thúc."""
        (self.root / "media").mkdir()
        shutil.copyfile(ROOT / "media/mediamtx.yml", self.root / "media/mediamtx.yml")
        shutil.copyfile(ROOT / "compose.yaml", self.root / "compose.yaml")
        self.start(media=True)
        self.assertIsNone(self.process.poll(), self.output.read_text())
        self.assertIn("MediaMTX Docker sẵn sàng", self.output.read_text())
        line = next(
            line
            for line in self.output.read_text().splitlines()
            if line.startswith("[mediamtx] PID")
        )
        media_pid = int(line.split()[2])
        self.process.send_signal(signal.SIGINT)
        self.assertEqual(self.process.wait(timeout=15), 0)
        with self.assertRaises(ProcessLookupError):
            os.kill(media_pid, 0)
        self.assert_ports_released()
        project = (
            "visionkit-"
            + hashlib.sha256(str(self.root / "data").encode()).hexdigest()[:10]
        )
        result = subprocess.run(
            [
                "docker",
                "ps",
                "--all",
                "--quiet",
                "--filter",
                f"label=com.docker.compose.project={project}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), "", "Container fixture chưa được dọn")

    def test_proxy_readiness_and_sigint_cleanup(self) -> None:
        """Web dùng đúng backend, backend dùng đúng AI; Ctrl+C thu hồi cả ba group."""
        self.start()
        self.assertIsNone(self.process.poll(), self.output.read_text())
        self.assertIn("Proxy frontend kết nối được backend", self.output.read_text())
        with urllib.request.urlopen(
            f"http://127.0.0.1:{self.ports['web']}/api/v1/health"
        ) as response:
            self.assertEqual(json.load(response), {"status": "ok"})
        self.process.send_signal(signal.SIGINT)
        self.assertEqual(self.process.wait(timeout=15), 0)
        self.assert_ports_released()

    def test_stop_command_shuts_down_owned_session(self) -> None:
        """--stop xác minh PID giữ lock và đóng phiên đang chạy trong project fixture."""
        self.start()
        self.assertIsNone(self.process.poll(), self.output.read_text())
        result = subprocess.run(
            [sys.executable, str(self.root / "dev.py"), "--stop"],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.process.wait(timeout=5), 0)
        self.assert_ports_released()

    def test_duplicate_launcher_cannot_reopen_the_same_database(self) -> None:
        """Phiên thứ hai không được khởi tạo lại DB hay ngắt job của phiên đầu."""
        self.start()
        self.assertIsNone(self.process.poll(), self.output.read_text())
        result = subprocess.run(
            [sys.executable, str(self.root / "dev.py"), "--no-web"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Đã có một launcher", result.stderr)
        self.assertNotIn("PID", result.stdout)
        self.assertIsNone(self.process.poll())

    def test_supervise_restarts_ai_without_stopping_backend_or_web(self) -> None:
        """Chế độ dài hạn tạo PID AI mới sau crash và vẫn giữ backend/web hoạt động."""
        self.start(supervise=True)
        initial = self.output.read_text()
        ai_line = next(
            line for line in initial.splitlines() if line.startswith("[ai] PID")
        )
        old_pid = int(ai_line.split()[2])
        os.kill(old_pid, signal.SIGTERM)
        for _ in range(150):
            text = self.output.read_text()
            lines = [line for line in text.splitlines() if line.startswith("[ai] PID")]
            if len(lines) >= 2:
                break
            time.sleep(0.1)
        self.assertGreaterEqual(len(lines), 2, self.output.read_text())
        self.assertNotEqual(int(lines[-1].split()[2]), old_pid)
        self.assertIsNone(self.process.poll())
        with urllib.request.urlopen(
            f"http://127.0.0.1:{self.ports['backend']}/api/v1/health", timeout=5
        ) as response:
            self.assertEqual(response.status, 200)
        self.process.send_signal(signal.SIGINT)
        self.assertEqual(self.process.wait(timeout=15), 0)
        self.assert_ports_released()

    def test_service_crash_stops_remaining_groups(self) -> None:
        """AI dừng giữa phiên khiến launcher báo lỗi và đóng backend/web còn lại."""
        self.start()
        self.assertIsNone(self.process.poll(), self.output.read_text())
        line = next(
            line
            for line in self.output.read_text().splitlines()
            if line.startswith("[ai] PID")
        )
        ai_pid = int(line.split()[2])
        os.kill(ai_pid, signal.SIGTERM)
        self.assertEqual(self.process.wait(timeout=15), 1)
        self.assertIn("ai đã dừng", self.output.read_text())
        self.assert_ports_released()

    def test_startup_failure_cleans_started_services(self) -> None:
        """Web startup lỗi vẫn giải phóng backend/AI đã sẵn sàng."""
        (self.root / "web/server.mjs").write_text("process.exit(7);")
        self.start()
        self.assertEqual(self.process.wait(timeout=15), 1)
        self.assertIn("web đã dừng", self.output.read_text())
        self.assert_ports_released()
