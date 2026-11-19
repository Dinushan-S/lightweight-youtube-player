"""Tickets 05 (own playlists), 06 (view + pin state) and 07 (media keys)."""
import time

from src.player.controller import PlayerController
from src.player.database import DatabaseManager
from src.player.desktop import (VK_MEDIA_NEXT_TRACK, VK_MEDIA_PLAY_PAUSE, VK_MEDIA_PREV_TRACK,
                                dispatch_media_key)
from src.player.models import PlaybackState, Track
from src.player.queue_manager import QueueManager
from tests.test_controller import MockAudioEngine, MockResolver


def _t(i):
    return Track(video_id=f"v{i}", title=f"T{i}", channel="C", duration_sec=60, stream_url=f"http://s/{i}")


def _ctrl():
    db = DatabaseManager(db_path=":memory:")
    return PlayerController(engine=MockAudioEngine(), resolver=MockResolver(), db=db), db


def _ids(tracks):
    return [t.video_id for t in tracks]


# --- 05: own playlists -----------------------------------------------------------------
def test_create_add_rename_delete_local_playlist():
    ctrl, db = _ctrl()
    changes = []
    ctrl.add_playlists_listener(lambda: changes.append(1))

    pid = ctrl.create_playlist("Deep Work")
    for i in (1, 2, 1):  # the same song twice is allowed
        ctrl.add_to_playlist(pid, _t(i))
    assert _ids(db.get_playlist_tracks(pid)) == ["v1", "v2", "v1"]
    [p] = ctrl.get_playlists()
    assert (p["title"], p["source_type"], p["track_count"]) == ("Deep Work", "local", 3)

    ctrl.rename_playlist(pid, "  Lofi Focus ")
    ctrl.rename_playlist(pid, "   ")  # blank name is ignored
    assert ctrl.get_playlists()[0]["title"] == "Lofi Focus"

    ctrl.delete_playlist(pid)
    assert ctrl.get_playlists() == [] and db.get_playlist_tracks(pid) == []
    assert len(changes) == 6  # create, 3 adds, rename, delete (blank rename doesn't notify)


def test_open_playlist_edits_are_saved_in_order():
    ctrl, db = _ctrl()
    pid = ctrl.create_playlist("Mix")
    for i in range(4):
        ctrl.add_to_playlist(pid, _t(i))

    assert ctrl.play_playlist(pid) and ctrl.playlist_id == pid
    assert ctrl.current_track.video_id == "v0"

    ctrl.move_in_queue(3, 0)                       # v3 to the top
    ctrl.move_in_queue(1, 2)                       # v0 down one
    assert _ids(ctrl.queue_tracks) == ["v3", "v1", "v0", "v2"]
    assert _ids(db.get_playlist_tracks(pid)) == ["v3", "v1", "v0", "v2"]
    assert ctrl.queue_tracks[ctrl.queue_index].video_id == "v0"  # playing song followed its move

    ctrl.add_to_playlist(pid, _t(9))               # adding to the open playlist also queues it
    ctrl.remove_from_queue(1)
    assert _ids(ctrl.queue_tracks) == ["v3", "v0", "v2", "v9"]
    assert _ids(db.get_playlist_tracks(pid)) == ["v3", "v0", "v2", "v9"]


def test_empty_playlist_does_not_play_and_deleting_open_playlist_detaches_queue():
    ctrl, db = _ctrl()
    empty = ctrl.create_playlist("Empty")
    assert ctrl.play_playlist(empty) is False and ctrl.playlist_id is None

    pid = ctrl.create_playlist("Mix")
    ctrl.add_to_playlist(pid, _t(1))
    ctrl.add_to_playlist(pid, _t(2))
    ctrl.play_playlist(pid)
    ctrl.delete_playlist(pid)
    assert ctrl.playlist_id is None
    ctrl.move_in_queue(0, 1)  # queue still works, nothing is saved
    assert _ids(ctrl.queue_tracks) == ["v2", "v1"] and db.get_playlist_tracks(pid) == []


def test_add_pasted_link_to_playlist():
    ctrl, db = _ctrl()
    pid = ctrl.create_playlist("Mix")
    done = []
    ctrl.add_url_to_playlist_async(pid, "https://youtu.be/test12345", on_complete=done.append)
    deadline = time.monotonic() + 2
    while not done and time.monotonic() < deadline:
        time.sleep(0.01)
    assert done == [True]
    assert _ids(db.get_playlist_tracks(pid)) == ["test12345"]


def test_queue_move_keeps_shuffle_round():
    q = QueueManager()
    q.load_tracks([_t(i) for i in range(5)], start_index=2)
    q.toggle_shuffle()
    order_before = [q.tracks[i].video_id for i in q._shuffle_order]
    assert q.move(4, 0) and not q.move(0, 0) and not q.move(0, 9)
    assert q.current_track.video_id == "v2"
    assert [q.tracks[i].video_id for i in q._shuffle_order] == order_before  # same songs, same play order


# --- 06: view toggle + pin -----------------------------------------------------------------
def test_view_toggle_and_pin_state():
    ctrl, db = _ctrl()
    assert ctrl.view == "full"
    ctrl.set_view("mini")
    assert ctrl.view == "mini"
    ctrl.set_view("full")
    assert ctrl.view == "full"
    try:
        ctrl.set_view("tiny")
        assert False, "unknown view accepted"
    except ValueError:
        pass

    assert ctrl.dock_pinned is True  # on by default
    ctrl.set_dock_pinned(False)
    assert PlayerController(engine=MockAudioEngine(), resolver=MockResolver(), db=db).dock_pinned is False  # saved


# --- 07: media keys ------------------------------------------------------------------------
def test_media_keys_map_to_controller_actions():
    ctrl, _ = _ctrl()
    ctrl.play_url("https://www.youtube.com/watch?v=test12345")
    assert ctrl.state == PlaybackState.PLAYING

    assert dispatch_media_key(ctrl, VK_MEDIA_PLAY_PAUSE)
    assert ctrl.state == PlaybackState.PAUSED
    dispatch_media_key(ctrl, VK_MEDIA_PLAY_PAUSE)
    assert ctrl.state == PlaybackState.PLAYING

    calls = []
    ctrl.next_track = lambda: calls.append("next")
    ctrl.prev_track = lambda: calls.append("prev")
    assert dispatch_media_key(ctrl, VK_MEDIA_NEXT_TRACK) and dispatch_media_key(ctrl, VK_MEDIA_PREV_TRACK)
    assert calls == ["next", "prev"]
    assert dispatch_media_key(ctrl, 0x41) is False  # not a media key


class _GatedResolver:
    """resolve_track blocks for links containing 'slow' until `release` is set (a wrong link that hangs)."""
    def __init__(self):
        import threading
        self.release = threading.Event()

    def resolve_track(self, url):
        if "slow" in url:
            self.release.wait(2)
        vid = url.rsplit("=", 1)[-1]
        return Track(video_id=vid, title=vid, channel="C", duration_sec=60, stream_url=f"http://s/{vid}")

    def resolve_playlist(self, url):
        self.release.wait(2)
        return "PL", [_t(1), _t(2)]


def _wait(pred):
    deadline = time.monotonic() + 2
    while not pred() and time.monotonic() < deadline:
        time.sleep(0.01)
    return pred()


def test_cancelled_link_is_dropped_when_its_lookup_finishes():
    r = _GatedResolver()
    ctrl = PlayerController(engine=MockAudioEngine(), resolver=r, db=DatabaseManager(db_path=":memory:"))
    done = []
    ctrl.open_url_async("https://www.youtube.com/watch?v=slow", on_complete=done.append)
    ctrl.cancel_open()
    r.release.set()
    assert _wait(lambda: done)
    assert done == [False] and ctrl.current_track is None and ctrl.state == PlaybackState.IDLE
    assert ctrl.get_history() == []


def test_new_link_replaces_one_still_loading():
    r = _GatedResolver()
    ctrl = PlayerController(engine=MockAudioEngine(), resolver=r, db=DatabaseManager(db_path=":memory:"))
    done = []
    ctrl.open_url_async("https://www.youtube.com/watch?v=slow", on_complete=done.append)
    ctrl.open_url_async("https://www.youtube.com/watch?v=good", on_complete=done.append)
    assert _wait(lambda: ctrl.current_track is not None) and ctrl.current_track.video_id == "good"
    r.release.set()
    assert _wait(lambda: len(done) == 2)
    assert ctrl.current_track.video_id == "good" and _ids(ctrl.queue_tracks) == ["good"]


def test_cancelled_playlist_import_is_not_saved():
    r = _GatedResolver()
    db = DatabaseManager(db_path=":memory:")
    ctrl = PlayerController(engine=MockAudioEngine(), resolver=r, db=db)
    done = []
    ctrl.open_url_async("https://www.youtube.com/playlist?list=PLx", on_complete=done.append)
    ctrl.cancel_open()
    r.release.set()
    assert _wait(lambda: done) and done == [False]
    assert db.get_playlists() == [] and ctrl.queue_tracks == []


def test_play_key_with_nothing_loaded_plays_last_history_song():
    ctrl, db = _ctrl()
    db.record_history(_t(7))
    dispatch_media_key(ctrl, VK_MEDIA_PLAY_PAUSE)
    deadline = time.monotonic() + 2
    while ctrl.state != PlaybackState.PLAYING and time.monotonic() < deadline:
        time.sleep(0.01)
    assert ctrl.state == PlaybackState.PLAYING
