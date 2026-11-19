"""Tests for playlist extraction, DB CRUD, and controller queue integration."""
import pytest
from unittest.mock import MagicMock, patch
from src.player.models import Track, PlaybackState, RepeatMode
from src.player.database import DatabaseManager
from src.player.queue_manager import QueueManager
from src.player.controller import PlayerController


# --- Playlist DB CRUD tests ---

def test_create_and_get_playlist():
    db = DatabaseManager(db_path=":memory:")
    db.create_playlist("pl1", "My Playlist", source_type="local")
    playlists = db.get_playlists()
    assert len(playlists) == 1
    assert playlists[0]["id"] == "pl1"
    assert playlists[0]["title"] == "My Playlist"


def test_add_and_get_playlist_tracks():
    db = DatabaseManager(db_path=":memory:")
    db.create_playlist("pl1", "Test", source_type="youtube_synced", source_url="https://youtube.com/playlist?list=PL1")
    tracks = [
        Track(video_id="a", title="A", channel="C1", duration_sec=100),
        Track(video_id="b", title="B", channel="C2", duration_sec=200),
    ]
    db.add_playlist_tracks("pl1", tracks)
    result = db.get_playlist_tracks("pl1")
    assert len(result) == 2
    assert result[0].video_id == "a"
    assert result[1].video_id == "b"
    assert result[0].title == "A"


def test_delete_playlist_cascades():
    db = DatabaseManager(db_path=":memory:")
    db.create_playlist("pl1", "Test", source_type="local")
    db.add_playlist_tracks("pl1", [
        Track(video_id="x", title="X", channel="C", duration_sec=50),
    ])
    db.delete_playlist("pl1")
    assert len(db.get_playlists()) == 0
    assert len(db.get_playlist_tracks("pl1")) == 0


# --- Resolver playlist extraction test ---

def test_resolve_playlist_returns_track_list():
    """Test that resolve_playlist extracts flat track metadata from a playlist URL."""
    from src.player.resolver import StreamResolver
    resolver = StreamResolver()

    fake_entries = [
        {"id": "v1", "title": "Song 1", "uploader": "Artist 1", "duration": 180, "url": "https://youtube.com/watch?v=v1"},
        {"id": "v2", "title": "Song 2", "uploader": "Artist 2", "duration": 240, "url": "https://youtube.com/watch?v=v2"},
        {"id": "gone", "title": None, "uploader": None, "duration": None},  # deleted video: skipped
    ]

    with patch("yt_dlp.YoutubeDL") as MockYDL:
        mock_instance = MagicMock()
        mock_instance.extract_info.return_value = {
            "id": "PL1",
            "title": "My Playlist",
            "_type": "playlist",
            "entries": fake_entries,
        }
        mock_instance.__enter__ = lambda self: mock_instance
        mock_instance.__exit__ = MagicMock(return_value=False)
        MockYDL.return_value = mock_instance

        playlist_title, tracks = resolver.resolve_playlist("https://youtube.com/playlist?list=PL1")

    assert playlist_title == "My Playlist"
    assert len(tracks) == 2
    assert tracks[0].video_id == "v1"
    assert tracks[0].title == "Song 1"
    assert tracks[1].video_id == "v2"


# --- Controller + Queue integration tests ---

def _make_mock_engine():
    engine = MagicMock()
    engine.load_stream = MagicMock()
    engine.pause = MagicMock()
    engine.resume = MagicMock()
    engine.stop = MagicMock()
    engine.start = MagicMock()
    engine.send_command = MagicMock()
    engine.seek = MagicMock()
    engine.set_volume = MagicMock()
    return engine


def _make_tracks(n=3):
    return [
        Track(
            video_id=str(i),
            title=f"Track {i}",
            channel="Artist",
            duration_sec=100 + i * 10,
            stream_url=f"http://stream/{i}",
        )
        for i in range(n)
    ]


def test_controller_load_playlist_and_play():
    """Loading a playlist into controller starts playing the first track."""
    engine = _make_mock_engine()
    db = DatabaseManager(db_path=":memory:")
    ctrl = PlayerController(engine=engine, db=db)
    tracks = _make_tracks(3)

    ctrl.load_playlist(tracks, start_index=0)

    assert ctrl.state == PlaybackState.PLAYING
    assert ctrl.current_track.video_id == "0"
    engine.load_stream.assert_called_once_with("http://stream/0")


def test_controller_next_track():
    engine = _make_mock_engine()
    db = DatabaseManager(db_path=":memory:")
    ctrl = PlayerController(engine=engine, db=db)
    ctrl.load_playlist(_make_tracks(3), start_index=0)

    ctrl.next_track()
    assert ctrl.current_track.video_id == "1"
    assert ctrl.state == PlaybackState.PLAYING


def test_controller_prev_track():
    engine = _make_mock_engine()
    db = DatabaseManager(db_path=":memory:")
    ctrl = PlayerController(engine=engine, db=db)
    ctrl.load_playlist(_make_tracks(3), start_index=1)

    ctrl.prev_track()
    assert ctrl.current_track.video_id == "0"
    assert ctrl.state == PlaybackState.PLAYING


def test_controller_auto_advance_on_end_file():
    """When engine fires end-file (eof), controller auto-advances to next track."""
    engine = _make_mock_engine()
    db = DatabaseManager(db_path=":memory:")
    ctrl = PlayerController(engine=engine, db=db)
    ctrl.load_playlist(_make_tracks(3), start_index=0)

    # Simulate end-of-file event from engine
    ctrl._handle_engine_event({"event": "end-file", "reason": "eof"})

    assert ctrl.current_track.video_id == "1"
    assert ctrl.state == PlaybackState.PLAYING


def test_controller_auto_advance_stops_at_end_repeat_off():
    """With repeat OFF, reaching end of queue transitions to IDLE."""
    engine = _make_mock_engine()
    db = DatabaseManager(db_path=":memory:")
    ctrl = PlayerController(engine=engine, db=db)
    ctrl.load_playlist(_make_tracks(2), start_index=1)

    ctrl._handle_engine_event({"event": "end-file", "reason": "eof"})

    assert ctrl.state == PlaybackState.IDLE


def test_controller_set_repeat_mode():
    engine = _make_mock_engine()
    db = DatabaseManager(db_path=":memory:")
    ctrl = PlayerController(engine=engine, db=db)
    ctrl.load_playlist(_make_tracks(2), start_index=0)

    ctrl.set_repeat_mode(RepeatMode.ALL)
    assert ctrl.repeat_mode == RepeatMode.ALL

    # At last track, next wraps around
    ctrl._current_index_override_for_test = 1
    ctrl._queue._current_index = 1
    ctrl.next_track()
    assert ctrl.current_track.video_id == "0"


def test_controller_toggle_shuffle():
    engine = _make_mock_engine()
    db = DatabaseManager(db_path=":memory:")
    ctrl = PlayerController(engine=engine, db=db)
    ctrl.load_playlist(_make_tracks(5), start_index=0)

    ctrl.toggle_shuffle()
    assert ctrl.is_shuffle is True

    ctrl.toggle_shuffle()
    assert ctrl.is_shuffle is False
