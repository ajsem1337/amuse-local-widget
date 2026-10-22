# Audit — 2026-10-23

Scope: local HTTP server, MPRIS integration, OBS interface, systemd installation
and repository checks. Baseline: `6493a28`.

| Finding | Impact | Resolution |
| --- | --- | --- |
| `/cover?path=...` reads arbitrary local files; wildcard CORS exposes responses to other origins | High | Replace filesystem arguments with identifiers for validated cover snapshots; remove wildcard CORS and reject foreign hosts/origins |
| Generic static routing exposes source, `.git` and parent paths | High | Explicit routes for the UI, metadata and registered covers |
| Each metadata field rediscovers its player | Medium | Select one player per snapshot, preferring playing players and supporting unknown MPRIS names |
| Backend never returns position or duration | Medium | Return seconds and convert MPRIS microseconds; preserve null for unavailable timing |
| Interval polling can overlap slow subprocess queries | Medium | Schedule each poll after completion, abort stalled fetches and share concurrent server snapshots |
| Repeated text/cover resets break marquee and reload artwork | Low | Update changed values only and measure actual text overflow |
| Explicit CSS display rules override `hidden` on artwork | Low | Honor hidden state consistently and show the fallback after image failure |
| Service instructions omit unit installation; interpreter path is distribution dependent | Low | Document unit copy/reload and use `/usr/bin/python3` |

Validation: 11 Python unit/HTTP tests and 5 JavaScript behavior tests passed.
Python compilation, workflow actionlint and `git diff --check` passed. The
systemd unit passed syntax verification (sandbox socket warnings only).
CI covers Python 3.11, 3.14 and 3.15; Actions are pinned to verified release
commits, with Dependabot configured for updates.

No third-party Python or JavaScript runtime packages are used. This environment
has no `playerctl` or OBS, so live MPRIS playback and an OBS Browser Source were
not exercised. The attempted headless browser smoke check timed out; frontend
behavior was verified using the Node.js regression suite instead.
