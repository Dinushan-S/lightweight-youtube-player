# Spec: Ultra-Lightweight YouTube Audio Player

## Problem Statement

When working and coding, the user listens to music playlists hosted on YouTube and YouTube Music. To do this currently, the user must keep a web browser instance running solely for audio playback.

Modern web browsers are resource-intensive: running YouTube in a browser tab routinely consumes between 1.0 GB and 2.5 GB of RAM, engages heavy GPU/CPU video decoders to render video frames the user never watches, and introduces visual distractions, background telemetry, and tab clutter. This causes noticeable performance degradation, fan noise, and battery drain during productivity hours.

Furthermore, the user lacks an unobtrusive, lightweight desktop interface to control music playback with hardware media keys, quickly paste YouTube links to play audio on-demand, track recent listening history, and manage local playlists without keeping a bulky browser open.

## Solution

A dedicated, ultra-low resource desktop audio player engineered specifically for productivity. The application extracts and streams YouTube audio-only streams (Opus 48kHz stereo, ~160kbps) with zero video frames decoded or rendered, slashing memory consumption to under 50–70 MB RAM and CPU usage to under 0.5%.

The player features a hybrid two-tier YouTube sync engine allowing instant synchronization of public and unlisted YouTube playlists via direct link pasting, alongside Google Device Flow authentication (`google.com/device`) to sync private playlists and liked music. Users can paste any individual YouTube or YouTube Music link to play audio immediately, organize tracks into local playlists, review recent playback history, and toggle seamlessly between a full library management interface and a minimal, always-on-top floating mini-player (`340x80 px`) with global Windows media key and system tray support.

## User Stories

1. As a developer, I want to listen to music from YouTube without running a web browser, so that I can save over 1 GB of RAM and prevent CPU spikes while coding.
2. As a user, I want the player to stream only audio data without downloading or decoding video frames, so that I conserve network bandwidth and eliminate GPU decoding overhead.
3. As a music listener, I want to receive the highest fidelity audio stream that YouTube provides (Opus 48 kHz stereo at ~160 kbps), so that my listening experience sounds crisp and CD-quality.
4. As a user, I want the player to automatically fall back to the highest available AAC stream if an Opus stream is absent for a specific track, so that playback never fails silently.
5. As a user, I want to paste any YouTube or YouTube Music video URL into the player, so that the audio begins playing immediately without requiring me to create a playlist first.
6. As a user, I want to paste a public or unlisted YouTube playlist link, so that the player imports all tracks into my local library without requiring any login credentials.
7. As a user, I want to click a "Refresh" button on any synced playlist, so that any new tracks added to the remote YouTube playlist are retrieved and updated in my player.
8. As a user with private playlists and liked music, I want to connect my YouTube account using Google Device Flow (`google.com/device`), so that I can sync my private music library without exposing browser cookie databases or dealing with browser locking issues.
9. As a user, I want to see my recent playback history with track titles, channel names, and timestamps, so that I can easily find and re-listen to songs I enjoyed recently.
10. As a user, I want to create custom local playlists within the application, so that I can curate my own track collections independent of YouTube's online library.
11. As a user, I want to add any currently playing song or pasted URL directly into an existing local playlist, so that I can build up collections while listening.
12. As a user, I want to reorder or remove tracks from my local playlists, so that my playlists reflect my current preferences.
13. As a user, I want an interactive seek bar that displays current playback time and total track duration, so that I can scrub to any point in the track smoothly.
14. As a user, I want play, pause, next track, and previous track controls, so that I can control my queue intuitively.
15. As a user, I want shuffle and repeat toggles, so that I can choose between sequential playback, looping a single track, or randomizing my playlist queue.
16. As a user, I want volume control with an instant mute toggle, so that I can adjust audio output without altering system-wide sound levels.
17. As a worker needing focus, I want a one-click shortcut (`Ctrl + M`) to collapse the player into an ultra-compact floating mini-player (`340x80 px`), so that the player occupies minimal screen space while I code.
18. As a developer with multiple overlapping windows, I want the floating mini-player to remain Always-on-Top with a toggleable pin icon, so that it stays visible above my IDE and terminal.
19. As a user working in full-screen applications, I want my physical keyboard and headset media keys (`Play/Pause`, `Next Track`, `Previous Track`) to control playback system-wide, so that I can change tracks without switching window focus.
20. As a user, I want the player to minimize directly to the Windows System Tray, so that my Windows Taskbar remains uncluttered during deep work sessions.
21. As a user, I want right-click options in the System Tray icon for quick play, pause, next, and quit, so that I can control audio directly from the notification area.
22. As a user, I want the player to operate completely offline for local database navigation and playlist curation, streaming tracks on-demand when an internet connection is available.
23. As a user, I want to see an audio stream telemetry badge (e.g., `Opus 160k (Audio-Only)`), so that I am assured of the audio quality and zero-video decoding mode.
24. As a user, I want track title and channel metadata to update instantaneously when a track changes, so that I always know what song is currently playing.
25. As a user, I want quick search filtering across the current playlist or history list, so that I can jump to a specific track in seconds.

## Implementation Decisions

### Architectural Separation & Seams
The application is structured into four cleanly decoupled subsystems:
1. **Application Controller (High Seam)**: The central orchestrator that manages playback state, queue transitions, user commands, and emits state updates to the UI.
2. **Audio Playback Engine**: A headless MPV child process communicating exclusively over a two-way JSON Inter-Process Communication (IPC) named pipe (`\\.\pipe\mpv_music_player`). The MPV binary is provisioned as a portable self-contained executable inside the application's local binary store.
3. **Stream & Metadata Resolver**: An extraction module wrapping the `yt-dlp` Python interface and Google Device Flow client. It resolves direct Opus audio stream URLs and extracts playlist metadata asynchronously on background threads to keep the UI completely non-blocking.
4. **Data Persistence Engine**: An embedded SQLite database (`player.db`) managing relational tables for playlists, playlist items, playback history, and application settings.

### Schema Decision
```sql
CREATE TABLE playlists (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL, -- 'youtube_synced' or 'local'
    source_url TEXT,
    last_synced_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE playlist_tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_id TEXT REFERENCES playlists(id) ON DELETE CASCADE,
    video_id TEXT NOT NULL,
    title TEXT NOT NULL,
    channel TEXT,
    duration_sec INTEGER,
    thumbnail_url TEXT,
    track_order INTEGER
);

CREATE TABLE history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    title TEXT NOT NULL,
    channel TEXT,
    duration_sec INTEGER,
    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    play_count INTEGER DEFAULT 1
);

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

### UI & Styling System
- Developed using Python `CustomTkinter` following Impeccable *Operate* mode principles (dark obsidian slate palette `#0b0f17`, high-contrast crisp typography, responsive layout).
- Implements two distinct view modes:
  - **Full Library View**: Dual-pane window with navigation sidebar (Library, Playlists, History), track table with search filtering, and bottom playback bar.
  - **Floating Mini-Player View**: A lightweight `340x80 px` card with track title, channel, elapsed/duration progress bar, play/pause, skip, and an always-on-top toggle pin.

### Hardware & System Integration
- Registers global Windows System Media Transport Controls (SMTC) and keyboard hooks for media keys (`VK_MEDIA_PLAY_PAUSE`, `VK_MEDIA_NEXT_TRACK`, `VK_MEDIA_PREV_TRACK`).
- Integrates with Windows System Tray (`pystray`) for background persistence on window close or minimize.

## Testing Decisions

### What Makes a Good Test
Tests must exclusively verify **observable external behavior** through the highest architectural seam (the Application Controller / State Machine). Tests must not inspect internal private implementation details or tie assertions to specific widget hierarchies.

A good test drives the controller via public methods (`play_url`, `pause`, `seek`, `next_track`, `sync_playlist`), observes state changes, event emissions, and database mutations, and verifies that audio engine commands and stream resolutions occur correctly.

### Seams to Test
- **Primary Seam: `PlayerController` API**:
  The entire application lifecycle can be tested through this single high seam. By providing a virtual/mocked IPC adapter for MPV and a mocked stream resolver, comprehensive end-to-end unit and integration tests can run headlessly and deterministically in milliseconds without network access or audio hardware.
- **Secondary Seam: `DatabaseManager` Contract**:
  Verified with an in-memory SQLite database (`:memory:`) to guarantee playlist CRUD, track reordering, history updates, and cascade deletions behave reliably.

### Prior Art
Standard controller/state machine testing patterns in media player architectures (such as mopidy, mpv shim controllers, and CLI music daemons) where playback engines and network resolvers are abstracted behind well-defined IPC boundaries.

## Out of Scope

- Video rendering, video window popup, or video stream downloading.
- Audio transcoding or converting YouTube streams into MP3/FLAC files on disk.
- Social features (comments, likes/dislikes posting, YouTube live chat).
- Cloud syncing of local playlists across multiple disparate machines.
- Heavy Electron or Chromium-based GUI runtimes.

## Further Notes

- Verified system tools: Python 3.12, `yt-dlp` (v2026.10.26), and `ffmpeg` (v9.0.2) are already available on the target Windows system.
- Memory target: Strictly <50–70 MB total working set during active streaming.
- CPU target: Strictly <0.5% average CPU consumption on modern multi-core processors.
