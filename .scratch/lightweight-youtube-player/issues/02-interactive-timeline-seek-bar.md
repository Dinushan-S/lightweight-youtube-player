# 02: Interactive Timeline & Live Seek Bar

**What to build:** Two-way IPC event streaming between MPV and the player UI. Displays elapsed time and total duration (`01:24 / 03:45`), updates a smooth progress bar each second, and allows dragging or clicking the slider to seek to any point in the audio stream.

**Blocked by:** 01: Core Audio Tracer Bullet

**Status:** done

- [x] MPV IPC event polling / callback listener for `time-pos` and `duration`
- [x] `PlayerController` seek method (`seek(seconds)`) and timeline position state properties
- [x] UI seek bar with drag/release handler and formatted timestamps (`MM:SS`)
- [x] Automated tests asserting timeline state changes and seek command dispatch through the `PlayerController` seam
