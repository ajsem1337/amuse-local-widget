# Amuse local widget

![Made with AI](https://img.shields.io/badge/Made%20with-AI-76ddcf)

Lightweight local “Now Playing” widget for OBS on Linux, inspired by Amuse.

**Made with AI.** This project was developed with AI assistance, including code, documentation, and testing.

Runs locally through `server.py`, while the included `amuse-widget.service` systemd unit allows automatic background startup.

## Requirements

* Linux
* Python 3.11 or newer
* `playerctl` 2.4 or newer
* OBS Studio

Install `playerctl`:

```sh
sudo pacman -S playerctl
```

## Start

```sh
cd ~/amuse-local-widget
python3 server.py
```

Run the server as your desktop user, in the same D-Bus session as the player.
No Python packages or virtual environment are needed.

OBS Browser Source (suggested size: 840 × 240):

```text
http://127.0.0.1:8765
```

## Systemd service

The `systemd/` directory contains the `amuse-widget.service` user unit.
It expects the repository at `~/amuse-local-widget`; adjust both paths in the
unit before copying it if you cloned elsewhere.

```sh
mkdir -p ~/.config/systemd/user
cp systemd/amuse-widget.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now amuse-widget.service
```

## Files

* `server.py` — local HTTP server providing track metadata
* `index.html` — OBS overlay/widget UI
* `systemd/amuse-widget.service` — optional background autostart service

## Uses

* `playerctl`
* MPRIS
* Python local server
* HTML/CSS OBS overlay

## Works with

* Spotify
* YouTube Music Desktop
* VLC
* most MPRIS-compatible Linux media players

## Style

The appearance can be customized inside the `<style>` section in `index.html`.

Styled with GNOME/libadwaita + Catppuccin Mocha.

## Player selection and progress

The widget selects a playing MPRIS player first, then a paused or stopped one.
Among players with the same state it prefers Chromium, Spotify, VLC, then
YouTube. Other MPRIS players work too.

To select a specific player, use a name from `playerctl -l`:

```sh
PLAYER=spotify python3 server.py
```

For systemd, run `systemctl --user edit amuse-widget.service` and add:

```ini
[Service]
Environment=PLAYER=spotify
```

Then restart with `systemctl --user restart amuse-widget.service`.

The progress bar uses the player's reported position and duration. It freezes
on pause. When timing is unavailable, it shows an indeterminate bar. Long track
names scroll without restarting on every refresh. Reduced motion follows the
browser's accessibility setting.

## Local API

* `GET /` or `/index.html` — widget interface
* `GET /metadata` — title, artist, album, artUrl, status, position, duration
* `GET /cover?id=...` — a recent local cover registered by the server

Position and duration are seconds, or `null` if unavailable. MPRIS track length
is converted from microseconds; see the [playerctl manual](https://github.com/altdesktop/playerctl/blob/master/doc/playerctl.1.in).
Concurrent metadata requests share a snapshot cached for 0.75 seconds.

The server listens on `127.0.0.1:8765` and accepts localhost hostnames only.
It rejects cross-site requests and does not provide CORS access. Only the
widget page, metadata and registered covers are served; filesystem paths and
source files are not public routes. Local PNG, JPEG, GIF and WebP covers are
limited to 4 MiB each. The eight most recent covers are held in memory. Remote
HTTP(S) cover URLs are loaded directly by the browser.

## Troubleshooting

* Missing metadata: check `playerctl -l`, then `playerctl status` in your desktop session.
* Service errors: run `journalctl --user -u amuse-widget.service -e`.
* After updating the unit: copy it again, run `systemctl --user daemon-reload`, then restart it.
* Port already in use: stop the existing widget process before starting another.

## Tests

Python tests use only the standard library. Frontend tests require Node.js 24
or newer for development, but Node.js is not needed to run the widget.

```sh
python3 -m unittest discover -s tests -v
node --test tests/widget.test.cjs
```

CI runs these checks on Python 3.11, 3.14 and 3.15.
