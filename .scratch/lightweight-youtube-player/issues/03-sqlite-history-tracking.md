# 03: SQLite History Tracking & Replay Panel

**What to build:** Embedded SQLite database that automatically records every played track (title, channel, duration, timestamp) upon playback start. A persistent "Recent History" panel in the UI allows the user to browse past tracks, search recent tracks, and click any item to replay it immediately.

**Blocked by:** 02: Interactive Timeline & Live Seek Bar

**Status:** done

- [x] SQLite `history` table schema and `DatabaseManager` adapter
- [x] Auto-recording track metadata on playback trigger
- [x] UI History sidebar/panel displaying recent tracks with relative timestamps
- [x] Clicking any history track replays audio immediately
- [x] Automated tests asserting history insertion, duplicate deduplication, and replay through `PlayerController`
