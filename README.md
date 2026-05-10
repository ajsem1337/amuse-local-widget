# Amuse local widget

Lightweight local “Now Playing” widget for OBS on Linux, inspired by Amuse.

Runs locally through `server.py`, while the included `amuse-widget.service` systemd unit allows automatic background startup.

## Requirements

* Linux
* Python 3
* `playerctl`
* OBS Studio

Install `playerctl`:

```fish id="2mbq6z"
sudo pacman -S playerctl
```

## Start

```fish id="k4kw6w"
cd ~/amuse-local-widget
python server.py
```

OBS Browser Source:

```text id="zjlwm1"
http://127.0.0.1:8765
```

## Systemd service

The `systemd/` directory contains the `amuse-widget.service` user unit.

```fish id="rg69cv"
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
