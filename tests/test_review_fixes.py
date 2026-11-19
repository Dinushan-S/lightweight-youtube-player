import threading
import time

from src.player.controller import PlayerController
from src.player.database import DatabaseManager
from src.player.models import Track, RepeatMode, PlaybackState
from src.player.queue_manager import QueueManager
from tests.test_controller import MockAudioEngine


def _t(i, stream=None):
    return Track(video_id=f"v{i}", title=f"T{i}", channel="C", duration_sec=60, stream_url=stream)


def test_shuffle_previous_after_running_off_the_end_does_not_crash():
    q = QueueManager()
    q.load_tracks([_t(i) for i in range(3)])
    q.toggle_shuffle()
    q.next_track(); q.next_track()           # at the last shuffled song
    assert q.next_track() is None            # past the end, twice
    assert q.next_track() is None
    assert q.prev_track() is not None        # used to raise IndexError


def test_shuffle_repeat_all_does_not_replay_the_song_that_just_ended():
    q = QueueManager()
    q.load_tracks([_t(i) for i in range(4)])
    q.repeat_mode = RepeatMode.ALL
    q.toggle_shuffle()
    for _ in range(3):
        q.next_track()
    last = q.current_track
    assert q.next_track() is not last        # wrap starts a new round on a different song


class FlakyResolver:
    """Resolves every video except the ones listed as dead."""
    def __init__(self, dead):
        self.dead = set(dead)

    def resolve_track(self, url):
        vid = url.rsplit("=", 1)[1]
        if vid in self.dead:
            return None
        return Track(video_id=vid, title=vid, channel="C", duration_sec=60, stream_url=f"http://s/{vid}")


def _wait(pred, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


def test_dead_video_in_playlist_is_skipped_not_fatal():
    engine = MockAudioEngine()
    ctrl = PlayerController(engine=engine, resolver=FlakyResolver(dead={"v1"}), db=DatabaseManager(db_path=":memory:"))
    ctrl.load_playlist([_t(i) for i in range(3)], start_index=1)   # starts on the dead one
    assert _wait(lambda: engine.loaded_url == "http://s/v2")      # skipped to the next song
    assert ctrl.state == PlaybackState.PLAYING


def test_all_dead_playlist_gives_up_instead_of_looping():
    engine = MockAudioEngine()
    ctrl = PlayerController(engine=engine, resolver=FlakyResolver(dead={"v0", "v1", "v2"}),
                            db=DatabaseManager(db_path=":memory:"))
    ctrl.set_repeat_mode(RepeatMode.ALL)
    ctrl.load_playlist([_t(i) for i in range(3)])
    assert _wait(lambda: ctrl.state == PlaybackState.IDLE and ctrl._resolve_failures == 0)
    time.sleep(0.2)
    assert threading.active_count() < 10 and engine.loaded_url is None


def test_late_failure_for_an_old_click_does_not_stop_the_new_song():
    gate = threading.Event()

    class SlowDead(FlakyResolver):
        def resolve_track(self, url):
            if url.endswith("v1"):
                gate.wait(2)
            return super().resolve_track(url)

    engine = MockAudioEngine()
    ctrl = PlayerController(engine=engine, resolver=SlowDead(dead={"v1"}), db=DatabaseManager(db_path=":memory:"))
    ctrl.load_playlist([_t(i) for i in range(3)], start_index=1)   # v1 resolving slowly (and will fail)
    ctrl.play_queue_index(2)                                      # user clicks v2 meanwhile
    assert _wait(lambda: engine.loaded_url == "http://s/v2")
    gate.set()                                                    # v1's failure arrives late
    time.sleep(0.2)
    assert ctrl.state == PlaybackState.PLAYING and engine.loaded_url == "http://s/v2"


def test_removing_the_playing_song_keeps_prev_next_and_repeat_one_sane():
    q = QueueManager()
    q.load_tracks([_t(i) for i in range(4)], start_index=2)   # v2 playing
    q.remove(2)
    assert q.prev_track().video_id == "v1"                     # the song before the gap, not two back
    q.load_tracks([_t(i) for i in range(4)], start_index=2)
    q.remove(2)
    assert q.next_track().video_id == "v3"                     # the song after the gap
    q.load_tracks([_t(i) for i in range(4)], start_index=2)
    q.repeat_mode = RepeatMode.ONE
    q.remove(2)
    assert q.next_track().video_id == "v3"                     # can't repeat a removed song: move on, not back


def test_removing_with_shuffle_does_not_restart_the_round():
    q = QueueManager()
    q.load_tracks([_t(i) for i in range(6)])
    q.toggle_shuffle()
    played = {q.current_track.video_id}
    for _ in range(2):
        played.add(q.next_track().video_id)
    upcoming = q._shuffle_order[q._shuffle_pos + 1:]
    q.remove(upcoming[0])                                      # remove a song not yet played
    rest = []
    while (t := q.next_track()) is not None:
        rest.append(t.video_id)
    assert len(rest) == 2 and not played & set(rest)           # only the 2 unplayed survivors, no repeats


def test_song_ending_while_the_users_pick_is_loading_does_not_skip_it():
    gate = threading.Event()

    class Slow(FlakyResolver):
        def resolve_track(self, url):
            gate.wait(2)
            return super().resolve_track(url)

    engine = MockAudioEngine()
    ctrl = PlayerController(engine=engine, resolver=Slow(dead=()), db=DatabaseManager(db_path=":memory:"))
    ctrl.load_playlist([_t(0, "http://s/v0"), _t(1), _t(2)])  # v0 playing; v1, v2 need resolving
    ctrl.next_track()                                          # user picks v1 (loading...)
    ctrl._handle_engine_event({"event": "end-file", "reason": "eof"})  # v0 ends meanwhile
    gate.set()
    assert _wait(lambda: engine.loaded_url == "http://s/v1")
    time.sleep(0.2)
    assert engine.loaded_url == "http://s/v1" and ctrl.queue_index == 1


def test_play_after_idle_fetches_a_fresh_stream():
    calls = []

    class Counting(FlakyResolver):
        def resolve_track(self, url):
            calls.append(url)
            return super().resolve_track(url)

    engine = MockAudioEngine()
    ctrl = PlayerController(engine=engine, resolver=Counting(dead=()), db=DatabaseManager(db_path=":memory:"))
    ctrl.play_url("https://www.youtube.com/watch?v=v7")
    ctrl._handle_engine_event({"event": "end-file", "reason": "error"})   # e.g. the link went 403
    assert ctrl.state == PlaybackState.IDLE
    ctrl.toggle_play_pause()
    assert _wait(lambda: len(calls) == 2 and ctrl.state == PlaybackState.PLAYING)


def test_removing_one_copy_of_a_duplicated_song_keeps_the_other():
    db = DatabaseManager(db_path=":memory:")
    db.create_playlist("PL", "x")
    db.add_playlist_tracks("PL", [_t(1), _t(2), _t(1)])
    db.remove_playlist_track("PL", "v1")
    assert [t.video_id for t in db.get_playlist_tracks("PL")] == ["v2", "v1"]


def test_bad_thumbnail_bytes_give_no_cover_instead_of_raising():
    from src.player.ui import CoverCache
    cache = CoverCache()
    cache._data["x"] = b"<html>captive portal</html>"
    assert cache.get("x", (64, 36)) is None
    assert cache.get("x", (64, 36)) is None   # stays "no cover", no retry storm


def test_engine_observers_sent_only_when_mpv_launches():
    sent = []

    class Engine(MockAudioEngine):
        running = False

        def start(self):
            if self.running:
                return False
            self.running = True
            return True

        def send_command(self, *args):
            sent.append(args[0])

    ctrl = PlayerController(engine=Engine(), resolver=FlakyResolver(dead=()), db=DatabaseManager(db_path=":memory:"))
    for i in range(5):
        ctrl.play_url(f"https://www.youtube.com/watch?v=v{i}")
    assert sent.count("observe_property") == 2   # time-pos + duration, once
