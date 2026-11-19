# 04: Public/Unlisted Playlist URL Import & Queue State Machine

**What to build:** User can paste any Public or Unlisted YouTube / YouTube Music playlist URL. Tracks are extracted in the background, stored in SQLite, and presented in an interactive track table. Features a complete queue state machine: auto-advance to next track on finish, Next, Previous, Shuffle, and Repeat modes.

**Blocked by:** 03: SQLite History Tracking & Replay Panel

**Status:** done

- [x] Background playlist metadata extraction without UI freeze
- [x] SQLite `playlists` and `playlist_tracks` schema tables
- [x] Queue state machine: Next, Previous, Shuffle, Repeat (Off, All, One)
- [x] Auto-advance on track completion event
- [x] UI tracklist view with active track highlighting
- [x] Automated tests asserting queue transitions, shuffle order, and repeat behaviors through `PlayerController`
