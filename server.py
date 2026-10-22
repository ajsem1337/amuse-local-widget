#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import stat
import subprocess
import threading
import time
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8765
MAX_COVER_BYTES = 4 * 1024 * 1024
COVERS: OrderedDict[str, tuple[bytes, str]] = OrderedDict()
COVER_LOCK = threading.Lock()
METADATA_LOCK = threading.Lock()
_metadata_cache: dict[str, object] = {}
_metadata_updated = 0.0


def run_raw_playerctl(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["playerctl", *args], stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", timeout=0.75,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def get_player() -> str:
    preferred = os.environ.get("PLAYER", "").strip()
    if preferred:
        return preferred

    # One discovery call, including status, keeps all fields on one player.
    output = run_raw_playerctl(
        "--all-players", "--format", "{{playerInstance}}\t{{status}}", "status",
    )
    players = []
    prefixes = ("chromium.instance", "spotify", "vlc", "youtube")
    for line in output.splitlines():
        player, separator, status = line.partition("\t")
        if separator and player:
            priority = next((i for i, p in enumerate(prefixes) if player.startswith(p)), len(prefixes))
            players.append(({"Playing": 0, "Paused": 1}.get(status, 2), priority, player))
    return min(players)[2] if players else ""


def run_playerctl(player: str, *args: str) -> str:
    return run_raw_playerctl(f"--player={player}", *args) if player else ""


def seconds(value: str, divisor: float = 1) -> float | None:
    try:
        result = float(value) / divisor
    except (ValueError, OverflowError):
        return None
    return result if math.isfinite(result) and result >= 0 else None


def image_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return ""


def cover_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username:
            return url
        if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
            return ""
        path = Path(unquote(parsed.path))
        if not path.is_absolute():
            return ""
        # NONBLOCK prevents a player-supplied FIFO from hanging the poll.
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_COVER_BYTES:
                return ""
            data = source.read(MAX_COVER_BYTES + 1)
    except (OSError, ValueError):
        return ""
    content_type = image_type(data)
    if not content_type or len(data) > MAX_COVER_BYTES:
        return ""
    token = hashlib.sha256(data).hexdigest()
    with COVER_LOCK:
        COVERS[token] = (data, content_type)
        COVERS.move_to_end(token)
        while len(COVERS) > 8:
            COVERS.popitem(last=False)
    return f"/cover?id={token}"


def get_metadata() -> dict[str, object]:
    player = get_player()
    return {
        "title": run_playerctl(player, "metadata", "xesam:title"),
        "artist": run_playerctl(player, "metadata", "xesam:artist"),
        "album": run_playerctl(player, "metadata", "xesam:album"),
        "artUrl": cover_url(run_playerctl(player, "metadata", "mpris:artUrl")),
        "status": run_playerctl(player, "status") or "Stopped",
        "position": seconds(run_playerctl(player, "position")),
        "duration": seconds(run_playerctl(player, "metadata", "mpris:length"), 1_000_000),
    }


def cached_metadata() -> dict[str, object]:
    global _metadata_cache, _metadata_updated
    with METADATA_LOCK:
        if not _metadata_cache or time.monotonic() - _metadata_updated >= 0.75:
            _metadata_cache = get_metadata()
            _metadata_updated = time.monotonic()
        return _metadata_cache.copy()


class Handler(BaseHTTPRequestHandler):
    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, fmt: str, *args) -> None:
        return

    def send_bytes(self, data: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self) -> None:
        port = self.server.server_port
        allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host", "").lower() not in allowed_hosts:
            self.send_bytes(b"Forbidden host", "text/plain", 403)
            return
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            self.send_bytes(b"Forbidden origin", "text/plain", 403)
            return
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{host}" for host in allowed_hosts}:
            self.send_bytes(b"Forbidden origin", "text/plain", 403)
            return
        try:
            parsed = urlsplit(self.path)
        except ValueError:
            self.send_bytes(b"Bad request", "text/plain", 400)
            return
        if parsed.scheme or parsed.netloc:
            self.send_bytes(b"Bad request", "text/plain", 400)
        elif parsed.path in ("/", "/index.html"):
            try:
                self.send_bytes((ROOT / "index.html").read_bytes(), "text/html; charset=utf-8")
            except OSError:
                self.send_bytes(b"Widget file unavailable", "text/plain", 500)
        elif parsed.path == "/metadata":
            self.send_bytes(json.dumps(cached_metadata(), allow_nan=False).encode("utf-8"),
                            "application/json; charset=utf-8")
        elif parsed.path == "/cover":
            query = parse_qs(parsed.query)
            tokens = query.get("id", [])
            with COVER_LOCK:
                cover = COVERS.get(tokens[0]) if set(query) == {"id"} and len(tokens) == 1 else None
            if cover:
                self.send_bytes(*cover)
            else:
                self.send_bytes(b"404", "text/plain", 404)
        else:
            self.send_bytes(b"404", "text/plain", 404)


def main() -> None:
    if not shutil.which("playerctl"):
        raise SystemExit("playerctl is required. Install it and run this server in your desktop session.")
    with ThreadingHTTPServer((HOST, PORT), Handler) as httpd:
        print(f"Now Playing widget: http://{HOST}:{PORT}", flush=True)
        print("OBS Browser Source -> URL above", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
