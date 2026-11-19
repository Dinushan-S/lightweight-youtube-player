# Product

<!-- impeccable:product-schema 1 -->

## Platform

windows-desktop (Python + CustomTkinter, native Windows window; not web, iOS or Android)

## Users
Planned for public release. Today the primary user is the author; later, anyone on Windows who listens to YouTube music while doing something else (work, study, coding) and wants it running quietly in the background.

## Product Purpose
Play YouTube songs and playlists as audio only, without a browser. Success: paste a link, music starts, and the player stays out of the way until you need it.

## Positioning
- Light on PC resources: audio only, no video decoding, no browser tabs (yt-dlp finds the stream, a hidden mpv process plays it).
- Stays out of the way: a small window, plus a docked mini player that collapses to a thin progress line at the top of the screen.
- No ads, no clutter: just songs, history, playlists and favorites.
- Plays whole YouTube playlists with shuffle and repeat.

## Operating Context
Runs on the user's Windows PC next to other work. Glanced at, controlled in short bursts (play/pause, next, volume), then ignored. Long sessions: big playlists (1,000+ songs), repeat loops.

## Capabilities and Constraints
- Inputs: YouTube video, playlist and watch-in-playlist links. History and imported playlists are stored in local SQLite.
- Controls: play/pause, previous, next, stop, shuffle, repeat (off/all/one), seek, volume with mute.
- Docked mini player: hover to expand (cover, controls, volume popup, playlist dropdown), drag along the top edge.
- Requested (2026-11-19): delete a song from the playlist; a Favorites list saved in the player; a favorite button in the docked mini player as well.
- Each new song takes ~5–13 s to start (YouTube link lookup). Stream links expire after ~6 h.
- Feature memo is kept in `memo.md` and updated on every change.

## Brand Commitments
Name in the window title: "Lightweight YouTube Player". Direction from the user: minimalist, simplest good look. No logo or other brand assets yet.

## Evidence on Hand
No users, reviews, metrics or press yet. Do not invent any.

## Product Principles
1. Music first, chrome last: every visible element must help play, find or control a song.
2. Light means light: no feature may add noticeable CPU or memory cost while playing.
3. Out of the way by default: the player never demands attention; the dock is the resting state.
4. One glance, one click: common actions (pause, next, volume, favorite) are reachable without hunting.
