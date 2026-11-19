# Lightweight YouTube Music Player — Memo

A small Windows desktop app that plays the **audio only** from YouTube videos and playlists. It uses no browser and decodes no video, so it stays light on CPU and RAM.

**Download:** `LightweightYouTubePlayer.exe` from the [latest GitHub release](https://github.com/Dinushan-S/lightweight-youtube-player/releases/latest): one file, no install, mpv included.
**Run from source:** `.venv\Scripts\python main.py` from the project folder.
**Tests:** `.venv\Scripts\python -m pytest -q`
**Build the .exe:** `.\build.ps1` (PyInstaller; output `dist\LightweightYouTubePlayer.exe`).

_Last updated: 2026-11-19_

---

## Features

### Look: three minimalist themes (switchable)
- The palette button (top-right, next to Dock) opens a small menu: **Match Windows (Graphite / Porcelain)**, **Graphite**, **Porcelain**, **Indigo**. The window rebuilds instantly in the new look; the song, queue, volume and open tab carry over. Your choice is saved and used next time.
- **Default is Match Windows:** Graphite when Windows is in dark mode, Porcelain in light mode. If you change the Windows mode while the player is open, it follows within about 2 seconds (it waits while docked, and switches when you restore the window). Picking a theme by name keeps that theme regardless of Windows.
  - **Graphite:** dark and completely flat, no panels or borders, white is the only accent.
  - **Porcelain:** light grey with white panels, hairline borders, one cobalt-blue accent.
  - **Indigo:** deep indigo fills the window, warm apricot accent, soft round shapes.
- Icons are Windows' own Fluent icon font (Segoe Fluent Icons, or Segoe MDL2 Assets on Windows 10). Text uses Segoe UI Variable.
- The docked mini player follows the chosen theme.

### Playing music
- **Paste a link and press Play** (or Enter). Works with:
  - a single video (`watch?v=…`, `youtu.be/…`)
  - a playlist (`playlist?list=…`)
  - a video inside a playlist (`watch?v=X&list=Y`): imports the whole playlist and starts at song X
- **Linked song starts first.** With a `watch?v=X&list=Y` link, song X starts playing (~9 s) while the rest of the playlist is still loading (~15 s for 1,300 songs).
- **Play with an empty link box.** Pressing Play (either button) with nothing loaded plays the most recent song from History. The empty screen says so: "Or press play to pick up your last song".
- **Now playing:** the song's cover image, title (two lines at most), channel and audio format (e.g. `Saregama Tamil · Opus 160k`).
- **Status text** appears under the title only when needed: "Finding the audio stream…" while loading, "Couldn't play that link. Check it and try again." on failure. The play/pause button shows whether it is playing.
- **Audio quality:** best audio-only stream, Opus first, then M4A.

### Player controls (under the seek bar)
`shuffle   previous   [ play / pause ]   next   repeat`. There is no Stop button; Pause covers it.

| Button | What it does |
|---|---|
| Play / Pause | Play / pause. If nothing is loaded, plays the pasted link, or else the last History song. If a song fails to load, Play tries the last song again. |
| Previous | Previous song in the queue. |
| Next | Next song in the queue. Works while paused (the new song plays). |
| Shuffle | Random order, keeping the current song first. Accent colour = on. |
| Repeat | Cycles Off → All (accent) → One (accent, "1" icon). |

### Favorites ♡
- **Heart button** under the song title (main window) and in the dock's control row. Click to add the playing song to Favorites; click again to remove it. Filled heart in the accent colour = favorite.
- **Favorites tab** in the side panel lists them, newest first. Click a song to play it; click its filled heart to remove it.
- Favorites are saved in the player's database and kept between launches.

### Removing songs from a playlist
- Every row in the **Tracklist** tab has an **✕**. It removes that song from the queue **and** from the saved copy of the playlist.
- Removing the song that is playing doesn't stop it; Next continues with the song that took its place.

### Repeat and the queue
- **Repeat One** loops the current song. **Repeat All** loops the whole queue (a single song counts as a one-song queue, so it loops too).
- **Repeat Off** stops at the end of the queue.
- A repeated song restarts instantly (no re-loading).
- A single song played after a playlist does **not** fall back into the old playlist.

### Seek bar
- Elapsed / total time under the bar. Drag and release to jump.
- Seeking while paused stays paused.

### Volume (bottom-right)
- **Slider 0–100%** in 1% steps, with the level shown next to it (e.g. `75%`).
- **Mouse wheel** over the slider: ±5% per notch.
- **Mute button.** The icon follows the level (loud, quiet, silent, muted). Mute keeps your level and unmute restores it; moving the slider also unmutes.
- Your volume is kept if the audio engine (mpv) restarts; it doesn't reset to 100%.

### Docked mini player (Dock button, next to Play)
- **Dock** hides the main window and pins a mini player to the **top edge of the screen** (top-right corner by default). It stays on top of other windows.
- **Collapsed:** just a thin progress line in the accent colour (320 px wide, not the full screen width) that fills as the song plays.
- **Hover the line:** it drops down to show:
  - the song's cover image, title, channel and time (`Sun TV · 01:23 / 03:45`)
  - one compact row: previous / play-pause / next, the **heart**, a speaker icon, and **Playlist**
  - **Volume:** hover the speaker icon and a volume bar with the % slides out just below it. It hides again when the mouse leaves the icon and the bar. Clicking the icon mutes or unmutes. Volume, mute and favorites stay in sync with the main window. The mouse wheel works on the bar once you've clicked anything in the dock (Windows only sends wheel events to the active window).
  - **Playlist:** opens the current queue under it (30 songs around the current one). Click a song to play it.
- **Move the mouse away:** it collapses back to the line (and closes the playlist).
- **Move it:** while it is open, drag the cover/title left or right to place it anywhere along the top.
- **Restore button** (top-right of the panel) brings back the full window.

### Side panel tabs
- **History:** every song you played, newest first, with a search box (title or channel). Click a song to play it again (it fetches a fresh stream, because saved stream addresses expire after a few hours).
- **Tracklist:** the current queue. The playing song is highlighted; click any song to jump to it, ✕ to remove it. Big playlists show 60 songs around the current one ("Showing 1–60 of 1328").
- **Favorites:** your hearted songs (see above).

### Saved data
- History, imported playlists, favorites and the chosen theme are stored in SQLite at `~/.local_ytplayer/player.db`.
- Importing the same playlist again replaces the saved copy (no duplicates). Deleted or private videos in a playlist are skipped.

---

## How it works (short)
- **UI:** CustomTkinter (`src/player/ui.py`). Themes are token sets in `THEMES`; every colour comes from the active theme. Icons are code points in the `Icon` class.
- **Brain:** `src/player/controller.py` (state, queue, repeat, volume, history, favorites, settings).
- **Queue / shuffle / repeat / remove logic:** `src/player/queue_manager.py`.
- **Finding the audio stream:** yt-dlp (`src/player/resolver.py`). It waits out YouTube's brief 403 on fresh links before playing.
- **Playing audio:** a hidden `mpv` process (`bin/mpv.exe`) controlled through a named pipe (`src/player/mpv_engine.py`).
- **Storage:** `src/player/database.py` (history, playlists, favorites, settings).
- **Mini player:** `src/player/mini_player.py`. Cover images come from `i.ytimg.com`, decoded with Pillow, cached in `CoverCache` (shared by both windows).
- **App icon:** `assets/icon.ico` (window and .exe). README screenshots: `assets/screenshots/`.
- **Packaging:** `build.ps1` bundles the app, `bin/mpv.exe` and `bin/vulkan-1.dll` into one `.exe` with PyInstaller.

## Known limits
- Each new song takes ~5–13 s to start (YouTube link lookup).
- A song looped for more than ~6 hours stops with a load error (the stream address expires).
- Previous / Next do nothing with a single song unless Repeat is on.
- If the app is killed instead of closed (Task Manager, crash), its mpv can keep running in the background until ended in Task Manager.
- The `.exe` isn't code-signed, so Windows SmartScreen may warn on first launch (More info → Run anyway).
- The mini player moves along the top of the **main** monitor only, and its position resets to the top-right each time you dock.
- The dock's playlist has no ✕ remove; remove songs from the main window's Tracklist.
- Small icons on coloured buttons can show faint colour fringes (Windows ClearType text smoothing).
- One playlist-import test fails occasionally (timing race in the test setup; not seen in the app).

---

## Change log
- **2026-11-19:**
  - Fixes from a code review: shuffle + Previous after the end no longer crashes; shuffle + Repeat All no longer replays the song that just ended; a deleted/private video in a playlist is skipped instead of stopping playback (it gives up after every song in a row fails); a slow failed lookup can no longer stop a newer song; mpv position listeners are registered once per mpv start instead of per song, so the UI no longer slows down over long sessions; background loading errors no longer leave the player stuck.
  - Each copy of the app now talks to its own mpv (the pipe name includes the process id).
  - Windows `.exe` build (`build.ps1`), app icon, README with a download link, MIT license and third-party notices. Published on GitHub.
- **2026-11-19:**
  - Removed the Stop button (the unlabeled square in the volume row); Pause covers it.
- **2026-11-19:**
  - Theme default now follows Windows: "Match Windows" uses Graphite in dark mode and Porcelain in light mode, and switches live. Indigo and the fixed themes stay in the menu.
  - Fixed: switching between a dark and a light theme printed `TclError: bad window path name …` in the terminal.
- **2026-11-19:**
  - New minimalist redesign with three switchable themes (Graphite, Porcelain, Indigo) and a palette menu; the choice is saved.
  - Windows Fluent icons replace the Unicode symbols; cover image now shows in the main window too.
  - "PLAYING/PAUSED" label removed; status text only appears while loading or on errors.
  - Added Favorites (heart in the main window and the dock, Favorites tab).
  - Added ✕ to remove a song from the Tracklist (also removes it from the saved playlist).
- **2026-11-19:**
  - Added the docked mini player: progress line at the top of the screen, hover panel with cover, previous/play/next and a playlist dropdown, drag to move, restore button.
  - New dependency: Pillow (for cover images).
  - Dock got a compact volume control: a speaker icon whose volume bar pops out below it on hover.
  - Mouse wheel volume now counts every notch (Windows can merge several notches into one event).
- **2026-11-19:**
  - Controls moved into the Now Playing card with monochrome icons.
  - Added volume % readout, mouse-wheel volume, and Mute.
  - Fixed: seek while paused showed pause; Next/Prev while paused played silence; Play after Stop did nothing; volume reset to 100% after Stop.
  - Play with no link plays the last History song.
  - History clicks now fetch a fresh stream.
  - Repeat now works for single songs.
  - A single song played after a playlist no longer jumps back into that playlist.
- **2026-11-19:** First version: link and playlist playback, queue, shuffle/repeat, history, playlist import.
