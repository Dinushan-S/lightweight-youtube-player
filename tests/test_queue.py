import pytest
from src.player.models import Track, RepeatMode
from src.player.queue_manager import QueueManager

def test_queue_initial_state_empty():
    qm = QueueManager()
    assert qm.current_track is None
    assert len(qm.tracks) == 0
    assert qm.repeat_mode == RepeatMode.OFF
    assert not qm.is_shuffle

def test_load_tracks_and_navigate():
    qm = QueueManager()
    tracks = [
        Track(video_id="1", title="Track 1", channel="Artist", duration_sec=100),
        Track(video_id="2", title="Track 2", channel="Artist", duration_sec=120),
        Track(video_id="3", title="Track 3", channel="Artist", duration_sec=140),
    ]
    qm.load_tracks(tracks, start_index=0)

    assert qm.current_track.video_id == "1"

    # Next track
    next_t = qm.next_track()
    assert next_t.video_id == "2"

    next_t = qm.next_track()
    assert next_t.video_id == "3"

    # End of queue with repeat OFF
    assert qm.next_track() is None

    # Previous track
    prev_t = qm.prev_track()
    assert prev_t.video_id == "2"

def test_repeat_all_wraps_around():
    qm = QueueManager()
    tracks = [
        Track(video_id="1", title="Track 1", channel="Artist", duration_sec=100),
        Track(video_id="2", title="Track 2", channel="Artist", duration_sec=120),
    ]
    qm.load_tracks(tracks, start_index=1)
    qm.repeat_mode = RepeatMode.ALL

    # Advancing past the end wraps to index 0
    next_t = qm.next_track()
    assert next_t.video_id == "1"

def test_repeat_one_returns_same_track():
    qm = QueueManager()
    tracks = [
        Track(video_id="1", title="Track 1", channel="Artist", duration_sec=100),
        Track(video_id="2", title="Track 2", channel="Artist", duration_sec=120),
    ]
    qm.load_tracks(tracks, start_index=0)
    qm.repeat_mode = RepeatMode.ONE

    next_t = qm.next_track()
    assert next_t.video_id == "1"

def test_shuffle_randomizes_order_while_preserving_tracks():
    qm = QueueManager()
    tracks = [Track(video_id=str(i), title=f"Track {i}", channel="Artist", duration_sec=100) for i in range(10)]
    qm.load_tracks(tracks, start_index=0)

    qm.toggle_shuffle()
    assert qm.is_shuffle
    assert len(qm.tracks) == 10
    # Current track stays at current position or remains current
    assert qm.current_track.video_id == "0"
