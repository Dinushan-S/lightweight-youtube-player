"""Ticket 04: playlist import, tracklist playback and queue transitions, driven through PlayerController."""
import threading
import time
from unittest.mock import MagicMock

import pytest
from src.player.controller import PlayerController, is_playlist_url
from src.player.database import DatabaseManager
from src.player.models import PlaybackState, RepeatMode, Track

PLAYLIST_URL = "https://www.youtube.com/playlist?list=PLabc"


class FakeResolver:
    def __init__(self, playlist_tracks=None):
        self._playlist_tracks = playlist_tracks if playlist_tracks is not None else [
            Track(video_id=f"v{i}", title=f"Song {i}", channel="Artist", duration_sec=100 + i)
            for i in range(3)
        ]

    def resolve_playlist(self, url):
        return ("My Mix", list(self._playlist_tracks))

    def resolve_track(self, url):
        vid = url.split("v=")[-1]
        return Track(video_id=vid, title=vid, channel="Artist", duration_sec=100,
                     stream_url=f"http://stream/{vid}", format_badge="Opus 160k")


def _wait_for(pred, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return False


def _make_controller(resolver=None):
    engine = MagicMock()
    db = DatabaseManager(db_path=":memory:")
    ctrl = PlayerController(engine=engine, resolver=resolver or FakeResolver(), db=db)
    return ctrl, engine, db


def _import_and_wait(ctrl, url=PLAYLIST_URL):
    done = threading.Event()
    results = []
    ctrl.import_playlist_async(url, on_complete=lambda ok: (results.append(ok), done.set()))
    assert done.wait(3.0)
    return results[0]


def _tracks_with_streams(n=5):
    return [
        Track(video_id=str(i), title=f"T{i}", channel="A", duration_sec=100, stream_url=f"http://s/{i}")
        for i in range(n)
    ]


@pytest.mark.parametrize("url, expected", [
    ("https://www.youtube.com/playlist?list=PLabc", True),
    ("https://music.youtube.com/playlist?list=OLAK5uy_x", True),
    ("https://www.youtube.com/watch?v=abc", False),
    ("https://www.youtube.com/watch?v=abc&list=PLabc", True),
    ("https://youtu.be/abc", False),
])
def test_is_playlist_url(url, expected):
    assert is_playlist_url(url) is expected


def test_import_stores_playlist_and_starts_playing_first_track():
    ctrl, engine, db = _make_controller()

    assert _import_and_wait(ctrl) is True

    assert [p["id"] for p in db.get_playlists()] == ["PLabc"]
    assert [t.video_id for t in db.get_playlist_tracks("PLabc")] == ["v0", "v1", "v2"]
    assert [t.video_id for t in ctrl.queue_tracks] == ["v0", "v1", "v2"]
    assert _wait_for(lambda: ctrl.state == PlaybackState.PLAYING)
    assert ctrl.current_track.video_id == "v0"
    engine.load_stream.assert_called_with("http://stream/v0")
    # Queue keeps metadata only, so a later replay re-resolves a fresh (non-expired) stream URL.
    assert all(t.stream_url is None for t in ctrl.queue_tracks)


def test_reimport_replaces_stored_tracks_instead_of_duplicating():
    ctrl, _, db = _make_controller()

    _import_and_wait(ctrl)
    _import_and_wait(ctrl)

    assert len(db.get_playlists()) == 1
    assert len(db.get_playlist_tracks("PLabc")) == 3


def test_failed_playlist_import_reports_false_and_stores_nothing():
    ctrl, _, db = _make_controller(FakeResolver(playlist_tracks=[]))

    assert _import_and_wait(ctrl) is False
    assert db.get_playlists() == []
    assert ctrl.queue_tracks == []


def test_play_queue_index_jumps_and_resolves_selected_track():
    ctrl, engine, _ = _make_controller()
    _import_and_wait(ctrl)
    assert _wait_for(lambda: ctrl.state == PlaybackState.PLAYING)

    ctrl.play_queue_index(2)

    assert _wait_for(lambda: ctrl.current_track is not None and ctrl.current_track.video_id == "v2")
    assert ctrl.queue_index == 2
    engine.load_stream.assert_called_with("http://stream/v2")


def test_shuffle_visits_every_track_once_starting_with_current():
    ctrl, _, _ = _make_controller()
    ctrl.load_playlist(_tracks_with_streams(5), start_index=0)

    ctrl.toggle_shuffle()
    visited = [ctrl.current_track.video_id]
    for _ in range(4):
        ctrl.next_track()
        visited.append(ctrl.current_track.video_id)

    assert visited[0] == "0"
    assert sorted(visited) == ["0", "1", "2", "3", "4"]
    ctrl.next_track()  # repeat OFF: nothing after the last shuffled track
    assert ctrl.current_track.video_id == visited[-1]


def test_repeat_one_keeps_same_track_on_auto_advance():
    ctrl, _, _ = _make_controller()
    ctrl.load_playlist(_tracks_with_streams(3), start_index=1)
    ctrl.set_repeat_mode(RepeatMode.ONE)

    ctrl._handle_engine_event({"event": "end-file", "reason": "eof"})

    assert ctrl.current_track.video_id == "1"
    assert ctrl.state == PlaybackState.PLAYING


def test_engine_load_error_leaves_playing_state():
    ctrl, _, _ = _make_controller()
    ctrl.play_url("https://www.youtube.com/watch?v=abc")
    assert ctrl.state == PlaybackState.PLAYING
    ctrl._handle_engine_event({"event": "end-file", "reason": "error", "file_error": "loading failed"})
    assert ctrl.state == PlaybackState.IDLE


def test_watch_url_with_list_imports_playlist_starting_at_v():
    ctrl, _, _ = _make_controller()
    assert _import_and_wait(ctrl, "https://www.youtube.com/watch?v=v1&list=PLabc")
    assert ctrl.queue_index == 1


def test_only_natural_end_of_file_auto_advances():
    ctrl, _, _ = _make_controller()
    assert _import_and_wait(ctrl)
    assert _wait_for(lambda: ctrl.state == PlaybackState.PLAYING)
    ctrl._handle_engine_event({"event": "end-file", "reason": "stop"})  # mpv replacing the file
    assert ctrl.queue_index == 0
    ctrl._handle_engine_event({"event": "end-file", "reason": "eof"})
    assert ctrl.queue_index == 1


def test_linked_song_plays_before_playlist_finishes_loading():
    gate = threading.Event()

    class SlowPlaylistResolver(FakeResolver):
        def resolve_playlist(self, url):
            assert gate.wait(3.0)
            return super().resolve_playlist(url)

    ctrl, engine, _ = _make_controller(SlowPlaylistResolver())
    done = threading.Event()
    ctrl.open_url_async("https://www.youtube.com/watch?v=v1&list=PLabc", on_complete=lambda ok: done.set())
    assert _wait_for(lambda: ctrl.state == PlaybackState.PLAYING)  # playing while the list is still loading
    assert ctrl.queue_tracks == []
    gate.set()
    assert done.wait(3.0)
    assert ctrl.queue_index == 1 and len(ctrl.queue_tracks) == 3
    assert engine.load_stream.call_count == 1  # the queue did not restart the song
