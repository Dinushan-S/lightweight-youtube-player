import sqlite3
import os
from typing import List, Optional, Dict, Any
from src.player.models import Track

DEFAULT_DB_PATH = os.path.join(
    os.path.expanduser("~"), ".local_ytplayer", "player.db"
)

class DatabaseManager:
    """Manages SQLite persistence for playback history and local playlists."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._memory_conn = None
        if self.db_path != ":memory:":
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        else:
            # Controller writes from worker threads, so the shared in-memory connection must allow it.
            self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_conn.row_factory = sqlite3.Row
            self._memory_conn.execute("PRAGMA foreign_keys = ON")
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._memory_conn:
            return self._memory_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    channel TEXT,
                    duration_sec INTEGER,
                    thumbnail_url TEXT,
                    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    play_count INTEGER DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS playlists (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    source_type TEXT NOT NULL, -- 'youtube_synced' or 'local'
                    source_url TEXT,
                    last_synced_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS playlist_tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_id TEXT REFERENCES playlists(id) ON DELETE CASCADE,
                    video_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    channel TEXT,
                    duration_sec INTEGER,
                    thumbnail_url TEXT,
                    track_order INTEGER
                );

                CREATE TABLE IF NOT EXISTS favorites (
                    video_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    channel TEXT,
                    duration_sec INTEGER,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
            """)

    def record_history(self, track: Track):
        """Records a played track into history or increments play count and bumps played_at."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO history (video_id, title, channel, duration_sec, thumbnail_url, played_at, play_count)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 1)
                ON CONFLICT(video_id) DO UPDATE SET
                    title = excluded.title,
                    channel = excluded.channel,
                    duration_sec = excluded.duration_sec,
                    thumbnail_url = excluded.thumbnail_url,
                    played_at = CURRENT_TIMESTAMP,
                    play_count = history.play_count + 1
            """, (track.video_id, track.title, track.channel, track.duration_sec, track.thumbnail_url))

    def get_history(self, limit: int = 50) -> List[Track]:
        """Returns the most recently played tracks."""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT video_id, title, channel, duration_sec, thumbnail_url
                FROM history
                ORDER BY played_at DESC
                LIMIT ?
            """, (limit,)).fetchall()

            return [
                Track(
                    video_id=r["video_id"],
                    title=r["title"],
                    channel=r["channel"] or "Unknown Artist",
                    duration_sec=r["duration_sec"] or 0,
                    thumbnail_url=r["thumbnail_url"],
                    stream_url=f"https://www.youtube.com/watch?v={r['video_id']}",
                )
                for r in rows
            ]

    def get_history_row(self, video_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM history WHERE video_id = ?", (video_id,)).fetchone()
            return dict(row) if row else None

    def clear_history(self):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM history")

    # --- Playlist CRUD ---

    def create_playlist(self, playlist_id: str, title: str, source_type: str = "local",
                        source_url: Optional[str] = None):
        """Create a new playlist entry."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO playlists (id, title, source_type, source_url, last_synced_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (playlist_id, title, source_type, source_url))

    def get_playlists(self) -> List[Dict[str, Any]]:
        """Return all playlists."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM playlists ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    def add_playlist_tracks(self, playlist_id: str, tracks: List[Track]):
        """Add tracks to a playlist in order."""
        with self._get_connection() as conn:
            for i, t in enumerate(tracks):
                conn.execute("""
                    INSERT INTO playlist_tracks (playlist_id, video_id, title, channel, duration_sec, thumbnail_url, track_order)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (playlist_id, t.video_id, t.title, t.channel, t.duration_sec, t.thumbnail_url, i))

    def get_playlist_tracks(self, playlist_id: str) -> List[Track]:
        """Get all tracks in a playlist in order."""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT video_id, title, channel, duration_sec, thumbnail_url
                FROM playlist_tracks
                WHERE playlist_id = ?
                ORDER BY track_order
            """, (playlist_id,)).fetchall()
            return [
                Track(
                    video_id=r["video_id"],
                    title=r["title"],
                    channel=r["channel"] or "Unknown Artist",
                    duration_sec=r["duration_sec"] or 0,
                    thumbnail_url=r["thumbnail_url"],
                )
                for r in rows
            ]

    def delete_playlist(self, playlist_id: str):
        """Delete a playlist and its tracks (cascade)."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))

    def remove_playlist_track(self, playlist_id: str, video_id: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM playlist_tracks WHERE playlist_id = ? AND video_id = ?", (playlist_id, video_id))

    # --- Settings ---

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        with self._get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

    # --- Favorites ---

    def set_favorite(self, track: Track, on: bool):
        with self._get_connection() as conn:
            if on:
                conn.execute("""
                    INSERT OR IGNORE INTO favorites (video_id, title, channel, duration_sec)
                    VALUES (?, ?, ?, ?)
                """, (track.video_id, track.title, track.channel, track.duration_sec))
            else:
                conn.execute("DELETE FROM favorites WHERE video_id = ?", (track.video_id,))

    def is_favorite(self, video_id: str) -> bool:
        with self._get_connection() as conn:
            return conn.execute("SELECT 1 FROM favorites WHERE video_id = ?", (video_id,)).fetchone() is not None

    def get_favorites(self) -> List[Track]:
        """Newest favorite first."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT video_id, title, channel, duration_sec FROM favorites ORDER BY added_at DESC, rowid DESC"
            ).fetchall()
            return [
                Track(video_id=r["video_id"], title=r["title"], channel=r["channel"] or "Unknown Artist",
                      duration_sec=r["duration_sec"] or 0)
                for r in rows
            ]
