# 08: Google Device Flow OAuth for Private Playlists & Liked Music

**What to build:** Safe account connection without touching locked browser cookie databases. User opens a settings modal, views an 8-character code, authorizes at `google.com/device`, and syncs their private YouTube playlists and personal Liked Music collection into the player.

**Blocked by:** 04: Public/Unlisted Playlist URL Import & Queue State Machine

**Status:** ready-for-agent

- [ ] Google Device Flow client requesting YouTube Data API scopes
- [ ] Settings modal showing code and verification URL
- [ ] Token exchange and encrypted local storage
- [ ] Authenticated playlist and Liked Music import via `yt-dlp` / API adapter
- [ ] Automated tests asserting device flow polling, token persistence, and authenticated fetch via `PlayerController`
