# 01: Core Audio Tracer Bullet (Paste URL & Play with Volume/Pause)

**What to build:** The minimal vertical tracer bullet: launch the player, paste any YouTube audio link, start playback via the portable MPV engine using direct Opus 160k stream extraction, control Play, Pause, and Volume, and verify end-to-end behavior at the `PlayerController` seam with automated tests.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] Portable MPV binary bootstrap & headless IPC process manager (`mpv_music_player`)
- [x] Direct Opus stream extraction adapter wrapping `yt-dlp`
- [x] `PlayerController` public API supporting `play_url`, `pause`, `resume`, and `set_volume`
- [x] Minimal obsidian slate UI with URL input, Play/Pause button, and volume slider
- [x] Automated tests asserting observable playback state and audio controls through the `PlayerController` seam
