from src.player.controller import PlayerController
from src.player.database import DatabaseManager
from src.player.models import Track
from src.player.queue_manager import QueueManager
from tests.test_controller import MockAudioEngine, MockResolver


def _t(i):
    return Track(video_id=f"v{i}", title=f"T{i}", channel="C", duration_sec=60, stream_url=f"http://s/{i}")


def test_favorites_toggle_list_and_notify():
    ctrl = PlayerController(engine=MockAudioEngine(), resolver=MockResolver(), db=DatabaseManager(db_path=":memory:"))
    calls = []
    ctrl.add_favorites_listener(lambda: calls.append(1))

    ctrl.set_favorite(_t(1), True)
    ctrl.set_favorite(_t(2), True)
    ctrl.set_favorite(_t(1), True)  # already a favorite: no duplicate
    assert ctrl.is_favorite("v1") and ctrl.is_favorite("v2")
    assert sorted(t.video_id for t in ctrl.get_favorites()) == ["v1", "v2"]

    ctrl.set_favorite(_t(1), False)
    assert not ctrl.is_favorite("v1")
    assert [t.video_id for t in ctrl.get_favorites()] == ["v2"]
    assert len(calls) == 4


def test_queue_remove_keeps_playing_song_and_next_continues():
    q = QueueManager()
    q.load_tracks([_t(i) for i in range(4)], start_index=1)

    q.remove(3)                       # after current: index unchanged
    assert q.current_track.video_id == "v1"
    q.remove(0)                       # before current: index shifts down
    assert q.current_track.video_id == "v1"
    q.remove(q.current_index)         # the playing song itself
    assert [t.video_id for t in q.tracks] == ["v2"]
    assert q.next_track().video_id == "v2"  # Next goes to the song that took its place
    q.remove(0)
    assert q.tracks == [] and q.current_track is None and q.next_track() is None


def test_remove_from_queue_also_updates_saved_playlist():
    db = DatabaseManager(db_path=":memory:")
    ctrl = PlayerController(engine=MockAudioEngine(), resolver=MockResolver(), db=db)
    tracks = [_t(i) for i in range(3)]
    db.create_playlist("PL1", "My list")
    db.add_playlist_tracks("PL1", tracks)
    ctrl.load_playlist(tracks)
    ctrl._playlist_id = "PL1"  # set by _import_playlist in the app

    ctrl.remove_from_queue(1)
    assert [t.video_id for t in ctrl.queue_tracks] == ["v0", "v2"]
    assert [t.video_id for t in db.get_playlist_tracks("PL1")] == ["v0", "v2"]
