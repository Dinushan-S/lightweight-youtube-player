# 05: Custom Local Playlist Authoring & Track Management

**What to build:** Full local playlist CRUD. User can create new custom playlists (e.g., "Deep Work", "Lofi Focus"), add any currently playing song or pasted URL into a playlist, reorder tracks, and remove tracks via right-click context menus.

**Blocked by:** 04: Public/Unlisted Playlist URL Import & Queue State Machine

**Status:** ready-for-agent

- [ ] SQLite CRUD for user-authored local playlists (`source_type = 'local'`)
- [ ] "+ Add to Playlist" dialog / menu on currently playing song and URL input
- [ ] UI context menu for track deletion and reordering within local playlists
- [ ] Automated tests asserting local playlist creation, track addition, deletion, and order preservation
