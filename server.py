#!/usr/bin/env python3
from __future__ import annotations

import json
import mimetypes
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8765


def run_playerctl(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["playerctl", *args],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1.5,
        ).strip()
    except Exception:
        return ""


def get_metadata() -> dict[str, str]:
    title = run_playerctl("metadata", "xesam:title")
    artist = run_playerctl("metadata", "xesam:artist")
    album = run_playerctl("metadata", "xesam:album")
    art_url = run_playerctl("metadata", "mpris:artUrl")
    status = run_playerctl("status") or "Stopped"

    if art_url.startswith("file://"):
        art_url = "/cover?path=" + art_url.removeprefix("file://")

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "artUrl": art_url,
        "status": status,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def send_bytes(self, data: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/":
            self.send_file(ROOT / "index.html")
            return

        if parsed.path == "/metadata":
            data = json.dumps(get_metadata()).encode("utf-8")
            self.send_bytes(data, "application/json; charset=utf-8")
            return

        if parsed.path == "/cover":
            query = parsed.query
            if query.startswith("path="):
                raw_path = unquote(query[5:])
                file_path = Path(raw_path)
                if file_path.exists() and file_path.is_file():
                    ctype = mimetypes.guess_type(str(file_path))[0] or "image/jpeg"
                    self.send_bytes(file_path.read_bytes(), ctype)
                    return

            self.send_bytes(b"", "text/plain", 404)
            return

        self.send_file(ROOT / parsed.path.lstrip("/"))

    def send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_bytes(b"404", "text/plain", 404)
            return

        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_bytes(path.read_bytes(), ctype)


def main() -> None:
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Now Playing widget: http://{HOST}:{PORT}")
    print("OBS Browser Source -> URL above")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
