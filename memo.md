# Lightweight YouTube Music Player — Memo

A small Windows desktop app that plays the **audio only** from YouTube videos and playlists. It uses no browser and decodes no video, so it stays light on CPU and RAM.

**Run it:** `.venv\Scripts\python main.py` from the project folder.
**Tests:** `.venv\Scripts\python -m pytest -q`

_Last updated: 2026-11-19_

---

## Features

### Playing music
- **Paste a link and press ▶ Play.** Works with:
  - a single video (`watch?v=…`, `youtu.be/…`)
  - a playlist (`playlist?list=…`)
  - a video inside a playlist (`watch?v=X&list=Y`): imports the whole playlist and starts at song X
- **Linked song starts first.** With a `watch?v=X&list=Y` link, song X starts playing (~9 s) while the rest of the playlist is still loading (~15 s for 1,300 songs).
- **Play with an empty link box.** Opening the app and pressing ▶ (either Play button) plays the most recent song from History.
- **Audio quality.** Picks the best audio-only stream: Opus first, then M4A. The format is shown as a badge, e.g. `⚡ OPUS 160k (Audio-Only)`.
- **Status line** shows `PLAYING`, `PAUSED`, `IDLE`, `STOPPED` or `RESOLVING AUDIO STREAM…`.

### Player controls (centred in the Now Playing card)
`🔀  ⏮  [ ▶ / ⏸ ]  ⏹  ⏭  🔁`

| Button | What it does |
|---|---|
| ▶ / ⏸ | Play / pause. If nothing is loaded, plays the pasted link, or else the last History song. After ⏹, plays the last song again. |
| ⏮ Previous | Previous song in the queue. |
| ⏭ Next | Next song in the queue. Works while paused (the new song plays). |
| ⏹ Stop | Stops playback. ▶ afterwards restarts the same song. |
| 🔀 Shuffle | Random order, keeping the current song first. Blue = on. |
| 🔁 Repeat | Cycles Off → All (🔁 blue) → One (🔂 blue). |

### Repeat and the queue
- **Repeat One** loops the current song. **Repeat All** loops the whole queue (a single song counts as a one-song queue, so it loops too).
- **Repeat Off** stops at the end of the queue.
- A repeated song restarts instantly (no re-loading).
- A single song played after a playlist does **not** fall back into the old playlist.

### Seek bar
- Shows elapsed / total time. Drag and release to jump.
- Seeking while paused stays paused.

### Volume (under the controls)
- **Slider 0–100%** in 1% steps, with the level shown next to it (e.g. `75%`).
- **Mouse wheel** over the slider: ±5% per notch.
- **Mute button.** The icon follows the level: 🔊 (50% or more), 🔉 (under 50%), 🔇 (muted or 0%). Mute keeps your level and unmute restores it; moving the slider also unmutes.
- Your volume is kept after ⏹ Stop (mpv restarting doesn't reset it to 100%).

### Docked mini player (⇱ Dock button, next to ▶ Play)
- **⇱ Dock** hides the main window and pins a mini player to the **top edge of the screen** (top-right corner by default). It stays on top of other windows.
- **Collapsed:** just a thin blue progress line (320 px wide, not the full screen width) that fills as the song plays.
- **Hover the line:** it drops down to show:
  - the song's cover image, title, channel and time (`Sun TV · 01:23 / 03:45`)
  - one compact row: ⏮ / ▶⏸ / ⏭, a speaker icon (🔊/🔉/🔇) and Playlist ▾
  - **Volume:** hover the speaker icon and a volume bar with the % slides out just below it. It hides again when the mouse leaves the icon and the bar. Clicking the icon mutes or unmutes. Volume and mute stay in sync with the main window. The mouse wheel works on the bar once you've clicked anything in the dock (Windows only sends wheel events to the active window).
  - **Playlist ▾**: opens the current queue under it (30 songs around the current one). Click a song to play it.
- **Move the mouse away:** it collapses back to the line (and closes the playlist).
- **Move it:** while it is open, drag the cover/title left or right to place it anywhere along the top.
- **⤢** (top-right of the panel) brings back the full window.

### Side panel tabs
- **History:** every song you played, newest first, with a search box (title or channel). Click a song to play it again (it fetches a fresh stream, because saved stream addresses expire after a few hours).
- **Tracklist:** the current queue. The playing song is highlighted; click any song to jump to it. Big playlists show 60 songs around the current one ("Showing 1-60 of 1328").

### Saved data
- History and imported playlists are stored in SQLite at `~/.local_ytplayer/player.db`.
- Importing the same playlist again replaces the saved copy (no duplicates). Deleted or private videos in a playlist are skipped.

---

## How it works (short)
- **UI:** CustomTkinter (`src/player/ui.py`).
- **Brain:** `src/player/controller.py` (state, queue, repeat, volume, history).
- **Queue / shuffle / repeat logic:** `src/player/queue_manager.py`.
- **Finding the audio stream:** yt-dlp (`src/player/resolver.py`). It waits out YouTube's brief 403 on fresh links before playing.
- **Playing audio:** a hidden `mpv` process (`bin/mpv.exe`) controlled through a named pipe (`src/player/mpv_engine.py`).
- **Storage:** `src/player/database.py`.
- **Mini player:** `src/player/mini_player.py` (cover images from `i.ytimg.com`, decoded with Pillow).

## Known limits
- Each new song takes ~5–13 s to start (YouTube link lookup).
- A song looped for more than ~6 hours stops with a load error (the stream address expires).
- ⏮ / ⏭ do nothing with a single song unless Repeat is on.
- The mini player moves along the top of the **main** monitor only, and its position resets to the top-right each time you dock.
- One playlist-import test fails occasionally (timing race in the test setup; not seen in the app).

---

## Change log
- **2026-11-19:**
  - Added the docked mini player (⇱ Dock): progress line at the top of the screen, hover panel with cover, ⏮ ⏸ ⏭ and a playlist dropdown, drag to move, ⤢ to restore.
  - New dependency: Pillow (for cover images).
  - Dock got a compact volume control: a speaker icon whose volume bar pops out below it on hover.
  - Mouse wheel volume now counts every notch (Windows can merge several notches into one event).
- **2026-11-19:**
  - Controls moved into the Now Playing card with monochrome icons.
  - Added volume % readout, mouse-wheel volume, and Mute.
  - Fixed: seek while paused showed ⏸; Next/Prev while paused played silence; ▶ after ⏹ did nothing; volume reset to 100% after Stop.
  - ▶ with no link plays the last History song.
  - History clicks now fetch a fresh stream.
  - Repeat now works for single songs.
  - A single song played after a playlist no longer jumps back into that playlist.
- **2026-11-19:** First version: link and playlist playback, queue, shuffle/repeat, history, playlist import.
