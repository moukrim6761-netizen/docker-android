import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
from urllib.parse import urlparse

from .adb import AdbClient, AdbCommandError, AdbConnectionError
from .config import settings

logger = logging.getLogger(__name__)
_UI_FILE = Path(__file__).with_name("index.html")


class UIRequestHandler(BaseHTTPRequestHandler):
    adb: AdbClient

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            try:
                content = _UI_FILE.read_bytes()
            except OSError:
                self.send_error(500, "UI file is unavailable")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if path == "/api/status":
            try:
                self.adb.connect(retries=1, delay=0)
                devices = self.adb.devices()
                current_window = self.adb.current_window()
            except (AdbCommandError, AdbConnectionError, OSError, subprocess.TimeoutExpired) as error:
                self._send_json(503, {"connected": False, "serial": self.adb.serial, "error": str(error)})
                return
            self._send_json(200, {
                "connected": True,
                "serial": self.adb.serial,
                "devices": devices,
                "current_window": current_window,
            })
            return

        self.send_error(404)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/action":
            self.send_error(404)
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0 or content_length > 4096:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(content_length))
            action = payload.get("action")
            if action == "navigate":
                url = payload.get("url", "").strip()
                if not url:
                    raise ValueError("URL cannot be empty")
                if "://" not in url:
                    url = f"https://{url}"
                output = self.adb.visit(url)
                result = {"status": "ok", "url": url, "output": output}
            elif action == "open_app":
                app_name = payload.get("app_name", "").strip()
                output = self.adb.open_app(app_name)
                result = {"status": "ok", "app_name": app_name, "output": output}
            elif action == "button":
                button = payload.get("button", "").strip()
                output = self.adb.press_button(button)
                result = {"status": "ok", "button": button, "output": output}
            else:
                raise ValueError("Unsupported action")
        except (json.JSONDecodeError, AttributeError, TypeError, ValueError) as error:
            self._send_json(400, {"error": str(error)})
            return
        except (AdbCommandError, AdbConnectionError, OSError, subprocess.TimeoutExpired) as error:
            self._send_json(503, {"error": str(error)})
            return

        self._send_json(200, result)

    def _send_json(self, status: int, payload: dict) -> None:
        content = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: object) -> None:
        logger.info("UI %s - %s", self.address_string(), format % args)


def serve_ui(adb: AdbClient) -> None:
    UIRequestHandler.adb = adb
    server = ThreadingHTTPServer((settings.ui_host, settings.ui_port), UIRequestHandler)
    logger.info("Android Cloud Phone UI listening on %s:%s", settings.ui_host, settings.ui_port)
    server.serve_forever()