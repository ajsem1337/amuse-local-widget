import concurrent.futures
import http.client
import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import server


class MetadataTests(unittest.TestCase):
    def test_active_player_wins_and_unknown_players_work(self):
        with patch.dict(os.environ, {"PLAYER": ""}), patch.object(
            server, "run_raw_playerctl", return_value="chromium.instance1\tPaused\nmpv\tPlaying"
        ):
            self.assertEqual(server.get_player(), "mpv")

    def test_preferred_player_does_not_trigger_discovery(self):
        with patch.dict(os.environ, {"PLAYER": "vlc"}), patch.object(server, "run_raw_playerctl") as run:
            self.assertEqual(server.get_player(), "vlc")
            run.assert_not_called()

    def test_metadata_pins_player_and_converts_microseconds(self):
        values = {
            ("metadata", "xesam:title"): "Zażółć 🎵", ("metadata", "xesam:artist"): "Artist",
            ("metadata", "mpris:length"): "240000000", ("position",): "61.25",
            ("status",): "Paused",
        }
        with patch.object(server, "get_player", return_value="spotify") as choose, patch.object(
            server, "run_playerctl", side_effect=lambda player, *args: values.get(args, "")
        ) as run:
            data = server.get_metadata()
        choose.assert_called_once()
        self.assertTrue(all(c.args[0] == "spotify" for c in run.call_args_list))
        self.assertEqual(data["position"], 61.25)
        self.assertEqual(data["duration"], 240)
        self.assertEqual(data["title"], "Zażółć 🎵")
        self.assertEqual(data["status"], "Paused")

    def test_unknown_and_invalid_times_are_null(self):
        for value in ("", "NaN", "Infinity", "-1", "not a time"):
            with self.subTest(value=value):
                self.assertIsNone(server.seconds(value))
        self.assertEqual(server.seconds("0"), 0)
        with patch.object(server, "get_player", return_value=""):
            self.assertEqual(server.get_metadata()["status"], "Stopped")

    def test_subprocess_errors_are_contained(self):
        for error in (FileNotFoundError(), subprocess.TimeoutExpired("playerctl", 0.75),
                      subprocess.CalledProcessError(1, "playerctl")):
            with patch.object(subprocess, "check_output", side_effect=error):
                self.assertEqual(server.run_raw_playerctl("status"), "")

    def test_concurrent_requests_share_snapshot(self):
        with patch.object(server, "_metadata_cache", {}), patch.object(
            server, "get_metadata", return_value={"status": "Stopped"}
        ) as read:
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: server.cached_metadata(), range(8)))
            self.assertEqual(len(results), 8)
            read.assert_called_once()


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.ThreadingHTTPServer((server.HOST, 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join()

    def request(self, path, headers=None):
        connection = http.client.HTTPConnection(server.HOST, self.httpd.server_port, timeout=3)
        try:
            connection.request("GET", path, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_ui_and_metadata(self):
        status, headers, data = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Now Playing", data)
        self.assertEqual(int(headers["Content-Length"]), len(data))
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        with patch.object(server, "cached_metadata", return_value={"title": "🎵", "position": None}):
            status, _, data = self.request("/metadata")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(data)["title"], "🎵")

    def test_source_and_traversal_are_unavailable(self):
        for path in ("/server.py", "/.git/config", "/../README.md", "/%2e%2e/README.md",
                     "/systemd/amuse-widget.service", "/cover?path=/etc/passwd"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 404)

    def test_host_and_cross_site_requests_are_blocked(self):
        for headers in ({"Host": "attacker.test"}, {"Origin": "https://attacker.test"},
                        {"Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.request("/metadata", headers)[0], 403)
        origin = f"http://127.0.0.1:{self.httpd.server_port}"
        self.assertEqual(self.request("/", {"Origin": origin})[0], 200)

    def test_only_registered_images_are_served(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "okładka #1&2.png"
            data = b"\x89PNG\r\n\x1a\ncover bytes"
            path.write_bytes(data)
            url = server.cover_url(path.as_uri())
            self.assertTrue(url.startswith("/cover?id="))
            path.unlink()  # Covers are immutable snapshots, not paths supplied by HTTP.
            status, headers, body = self.request(url)
            self.assertEqual((status, body), (200, data))
            self.assertEqual(headers["Content-Type"], "image/png")
            self.assertEqual(self.request(url + "&path=/etc/passwd")[0], 404)
            self.assertEqual(self.request("/cover?id=unknown")[0], 404)

    def test_non_images_and_oversize_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fake.png"
            for data in (b"secret", b"<svg onload='alert(1)'></svg>",
                         b"\x89PNG\r\n\x1a\n" + b"x" * server.MAX_COVER_BYTES):
                path.write_bytes(data)
                self.assertEqual(server.cover_url(path.as_uri()), "")
            fifo = Path(directory) / "pipe"
            os.mkfifo(fifo)
            self.assertEqual(server.cover_url(fifo.as_uri()), "")
        for url in ("javascript:alert(1)", "file://remote/etc/passwd", "file:///bad%00path"):
            self.assertEqual(server.cover_url(url), "")
        self.assertEqual(server.cover_url("https://example.com/art.jpg"), "https://example.com/art.jpg")


if __name__ == "__main__":
    unittest.main()
