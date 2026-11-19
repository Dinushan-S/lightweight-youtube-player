# Lightweight YouTube Music Player — Memo

A small Windows desktop app that plays the **audio only** from YouTube videos and playlists. It uses no browser and decodes no video, so it stays light on CPU and RAM.

**Download:** [LightweightYouTubePlayer.exe](https://github.com/Dinushan-S/lightweight-youtube-player/releases/latest/download/LightweightYouTubePlayer.exe) (direct link, always the newest version): one file, no install, mpv included.
**Releases:** [v1.1.0](https://github.com/Dinushan-S/lightweight-youtube-player/releases/tag/v1.1.0) (current) · [v1.0.0](https://github.com/Dinushan-S/lightweight-youtube-player/releases/tag/v1.0.0) · [all releases](https://github.com/Dinushan-S/lightweight-youtube-player/releases)
**Source code:** https://github.com/Dinushan-S/lightweight-youtube-player (public, MIT License)
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
- **Stuck on a wrong link?** While a link loads, the Play button turns into **Cancel**. Click it to stop waiting: the link text is selected so you can paste over it right away. Or just paste a new link and press **Enter** (or click a song in History/Favorites): the new one replaces the stuck one. A cancelled link never starts playing or gets saved, even if its lookup finishes later.
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

### Your own playlists
- **Playlists tab** (side panel) lists your playlists and the YouTube playlists you imported, with song counts ("12 songs · from YouTube"). The open one is highlighted.
  - **+ New playlist** at the top asks for a name.
  - **Click** a playlist to play it (switches to the Tracklist). **Right-click:** Play, Rename…, Delete…. The **✕** also deletes (asks first; songs stay in History and Favorites).
- **Adding songs:**
  - **＋ button** next to the heart under the title: adds the playing song to a playlist you pick, or makes a new one. If the link box holds a song link you haven't played yet, it adds **that link** instead (takes ~5–10 s to look up).
  - **Right-click any song** in History, Tracklist or Favorites → **Add to playlist** → pick one, or **New playlist…**.
  - Only your own playlists are offered (imported ones get replaced when you re-import them, so additions would be lost).
- **Editing an open playlist** (in the Tracklist): right-click a song → **Move up / Move down / Remove**, or click its ✕. Every change is saved to the playlist right away, in order. Adding a song to the open playlist also adds it to the end of the queue.
- The same song can be in a playlist more than once.

### Google account (your YouTube playlists and liked videos)
- **Google ▾** button in the Playlists tab (next to + New playlist) → **Connect Google account…**
  - A small window shows a code like `FJH-BSL-PZVW`. The code is already copied and **google.com/device** opens in your browser: paste the code, pick your account, click **Allow**. The window closes by itself and your playlists appear. **Cancel** stops waiting.
  - Access is **read-only** (`youtube.readonly`): the player can't change anything on your account.
- After connecting you get your **music playlists** (private ones too) plus **Liked music**, marked "· from YouTube". Click to play, like any playlist.
  - **Music only:** a song counts when YouTube files the video under its **Music** category. A playlist comes in when at least half of its videos are songs, and then only its songs. Liked music = the songs among your liked videos. So learning, tutorial and editing playlists stay out.
  - The window closes as soon as you're signed in; the status line shows "Getting your music playlists from YouTube…" while it fetches (~30 s for ~190 playlists, 8 at a time).
- **Sync:** automatic each time the player starts, or **Google ▾ → Sync now**. Each sync replaces the copies; playlists you deleted on YouTube (or that stopped being mostly music) disappear.
- **Disconnect…** forgets the sign-in (also tells Google) and removes the synced playlists. History and Favorites stay.
- The sign-in is saved **encrypted with Windows** (only your Windows account on this PC can read it).
- The Google button only shows when a Google client file (`client_secret*.json`) is next to the app (source) or bundled in the `.exe`.
- **Google Cloud setup:** YouTube Data API v3 on, OAuth consent screen in **Testing** with your account as a test user, client type **TVs and Limited Input devices** (the only type that allows code sign-in).

### Removing songs from a playlist
- Every row in the **Tracklist** tab has an **✕**. It removes that song from the queue **and** from the saved copy of the playlist.
- Removing the song that is playing doesn't stop it; Next continues with the song that took its place.

### Media keys and the system tray
- **Keyboard / headset media keys** (Play/Pause, Next, Previous) control the player from anywhere, even while another app is full-screen. Play/Pause with nothing loaded plays your last History song.
- **Tray icon** (bottom-right of the taskbar, maybe under the ^ arrow): **left-click** shows the player; **right-click** for Show player, Play/Pause (label follows the state), Next, Previous, **Quit**. Hovering it shows the playing song.
- **Closing (✕) or minimizing the window hides it to the tray; music keeps playing.** The first close shows a tip. Use **Quit** in the tray menu to really exit.

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

### Docked mini player (Dock button, next to Play, or **Ctrl+M**)
- **Dock** hides the main window and pins a mini player to the **top edge of the screen** (top-right corner by default). It stays on top of other windows unless you unpin it.
- **Ctrl+M** switches between the full window and the dock (in the dock it works after you've clicked it once, since Windows sends keys only to the active window).
- **Pin button** (top-right of the panel, next to Restore): accent pin = always on top; crossed-out pin = other windows can cover it. Your choice is saved.
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
- **Playlists:** your own, imported and Google playlists (see above).

### Saved data
- History, your playlists, imported and Google playlists, favorites, the chosen theme, the dock pin and the encrypted Google sign-in are stored in SQLite at `~/.local_ytplayer/player.db`.
- Importing the same playlist again replaces the saved copy (no duplicates). Deleted or private videos in a playlist are skipped.

---

## How it works (short)
- **UI:** CustomTkinter (`src/player/ui.py`). Themes are token sets in `THEMES`; every colour comes from the active theme. Icons are code points in the `Icon` class.
- **Brain:** `src/player/controller.py` (state, queue, repeat, volume, history, favorites, settings).
- **Queue / shuffle / repeat / remove logic:** `src/player/queue_manager.py`.
- **Finding the audio stream:** yt-dlp (`src/player/resolver.py`). It waits out YouTube's brief 403 on fresh links before playing.
- **Playing audio:** a hidden `mpv` process (`bin/mpv.exe`) controlled through a named pipe (`src/player/mpv_engine.py`).
- **Storage:** `src/player/database.py` (history, playlists, favorites, settings).
- **Media keys and tray:** `src/player/desktop.py` (media keys via Windows `RegisterHotKey`; tray via `pystray`).
- **Google account:** `src/player/google_account.py` (OAuth device flow, YouTube Data API v3, token encrypted with Windows DPAPI; standard library only).
- **Mini player:** `src/player/mini_player.py`. Cover images come from `i.ytimg.com`, decoded with Pillow, cached in `CoverCache` (shared by both windows).
- **App icon:** `assets/icon.ico` (window and .exe). README screenshots: `assets/screenshots/`.
- **Packaging:** `build.ps1` bundles the app, `bin/mpv.exe`, `bin/vulkan-1.dll` and (if present) `client_secret*.json` into one `.exe` with PyInstaller. The client file is gitignored, never committed.

## Known limits
- Each new song takes ~5–13 s to start (YouTube link lookup).
- A song looped for more than ~6 hours stops with a load error (the stream address expires).
- Previous / Next do nothing with a single song unless Repeat is on.
- If the app is killed instead of closed (Task Manager, crash), its mpv can keep running in the background until ended in Task Manager.
- The `.exe` isn't code-signed, so Windows SmartScreen may warn on first launch (More info → Run anyway).
- The mini player moves along the top of the **main** monitor only, and its position resets to the top-right each time you dock.
- The dock's playlist has no ✕ remove; remove songs from the main window's Tracklist.
- While the player runs it **owns the media keys**, so a browser or Spotify won't react to them (even when the player is paused). Quit from the tray to give them back. If another app grabbed them first, the player's media keys don't work (a note is printed when run from source).
- Reordering is one step at a time (Move up / Move down); there's no drag-and-drop.
- Unpinned dock + collapsed = a 6 px line that other windows can cover; bring it back with the tray icon's Show player.
- **Google sign-in lasts 7 days** while the Google Cloud app is in Testing mode; after that the player says "Google sign-in expired. Connect again." Only the test users listed in Google Cloud can connect.
- Private videos (even your own) and deleted videos in Google playlists are skipped: they can't be played without browser cookies.
- The music filter trusts the uploader's category: a song filed under another category is left out, and some non-songs filed as Music (e.g. guitar lessons) come in. A playlist with one song in two videos still counts.
- "Liked music" comes from your YouTube liked list; YouTube Music–only likes may not be in it.
- Editing or deleting a synced Google playlist in the player only changes the local copy; the next sync puts it back as it is on YouTube. They aren't offered under "Add to playlist".
- Small icons on coloured buttons can show faint colour fringes (Windows ClearType text smoothing).

---

## Change log
- **2026-11-19:**
  - Google account: connect with a code at google.com/device (Playlists tab → Google ▾); your YouTube music playlists (private ones too) and Liked music sync into the player, read-only, again at every start or with Sync now. Music only (YouTube's Music category; playlists at least half songs). Disconnect removes them. Sign-in saved encrypted with Windows DPAPI. No new dependencies.
  - Fixed the tests that failed now and then: the in-memory test database is shared by threads and now takes turns (the app itself was never affected; it opens a new connection per call).
- **2026-11-19:**
  - Your own playlists: Playlists tab (new, play, rename, delete), ＋ button and right-click "Add to playlist" on any song, pasted links can be added too, Move up / Move down in the Tracklist. Edits are saved in order.
  - Dock: **Ctrl+M** toggles full window ↔ dock; pin button for always-on-top (saved).
  - Media keys (keyboard and headset) work from any app; system tray icon with Show / Play-Pause / Next / Previous / Quit. Closing or minimizing now hides to the tray instead of quitting.
  - New dependency: `pystray` (tray icon).
  - A link that keeps loading can now be cancelled (Play becomes **Cancel**) or replaced by pasting a new link and pressing Enter. Before, Play stayed disabled until the bad link timed out.
  - Published as [release v1.1.0](https://github.com/Dinushan-S/lightweight-youtube-player/releases/tag/v1.1.0) carrying `LightweightYouTubePlayer.exe` (SHA-256 `632F53D37DB7F6A89F23DEC4C84C075A71A2C850B98B633DFD6D83CEFDCE619E`).
- **2026-11-19:**
  - Fixes from a code review: shuffle + Previous after the end no longer crashes; shuffle + Repeat All no longer replays the song that just ended; a deleted/private video in a playlist is skipped instead of stopping playback (it gives up after every song in a row fails); a slow failed lookup can no longer stop a newer song; mpv position listeners are registered once per mpv start instead of per song, so the UI no longer slows down over long sessions; background loading errors no longer leave the player stuck.
  - Each copy of the app now talks to its own mpv (the pipe name includes the process id).
  - Windows `.exe` build (`build.ps1`), app icon, README with a download link, MIT license and third-party notices.
  - Published on GitHub as a public repo, with [release v1.0.0](https://github.com/Dinushan-S/lightweight-youtube-player/releases/tag/v1.0.0) carrying `LightweightYouTubePlayer.exe` (SHA-256 `1BC6B33CDA1B2CAF70F7FCECF626C0810450ADC43B46E1ED1B92FCB340117253`).
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
