import pytest
from src.player.controller import PlayerController
from src.player.models import PlaybackState, Track
from src.player.database import DatabaseManager

class MockAudioEngine:
    def __init__(self):
        self.loaded_url = None
        self.is_paused = False
        self.volume = 100
        self.seek_position = 0.0
        self.is_running = True

    def load_stream(self, stream_url: str):
        self.loaded_url = stream_url
        self.is_paused = False

    def pause(self):
        self.is_paused = True

    def resume(self):
        self.is_paused = False

    def seek(self, seconds: float):
        self.seek_position = seconds

    def set_volume(self, volume: int):
        self.volume = max(0, min(100, volume))

    def stop(self):
        self.loaded_url = None
        self.is_paused = False

class MockResolver:
    def resolve_track(self, url: str) -> Track:
        return Track(
            video_id="test12345",
            title="Lofi Chill Beats",
            channel="Chill Station",
            duration_sec=180,
            stream_url="https://audio.googlevideo.com/videoplayback?itag=251",
            format_badge="Opus 160k"
        )

def test_initial_state_is_idle():
    engine = MockAudioEngine()
    resolver = MockResolver()
    controller = PlayerController(engine=engine, resolver=resolver, db=DatabaseManager(db_path=":memory:"))

    assert controller.state == PlaybackState.IDLE
    assert controller.current_track is None

def test_play_url_resolves_and_records_history():
    engine = MockAudioEngine()
    resolver = MockResolver()
    db = DatabaseManager(db_path=":memory:")
    controller = PlayerController(engine=engine, resolver=resolver, db=db)

    controller.play_url("https://www.youtube.com/watch?v=test12345")

    assert controller.state == PlaybackState.PLAYING
    assert controller.current_track is not None
    assert controller.current_track.title == "Lofi Chill Beats"
    assert engine.loaded_url == "https://audio.googlevideo.com/videoplayback?itag=251"

    # Verify history recorded in database
    history = controller.get_history()
    assert len(history) == 1
    assert history[0].video_id == "test12345"
    assert history[0].title == "Lofi Chill Beats"

def test_pause_and_resume_controls():
    engine = MockAudioEngine()
    resolver = MockResolver()
    controller = PlayerController(engine=engine, resolver=resolver, db=DatabaseManager(db_path=":memory:"))

    controller.play_url("https://www.youtube.com/watch?v=test12345")
    controller.pause()

    assert controller.state == PlaybackState.PAUSED
    assert engine.is_paused

    controller.resume()
    assert controller.state == PlaybackState.PLAYING
    assert not engine.is_paused

def test_set_volume_clamps_bounds():
    engine = MockAudioEngine()
    resolver = MockResolver()
    controller = PlayerController(engine=engine, resolver=resolver, db=DatabaseManager(db_path=":memory:"))

    controller.set_volume(85)
    assert controller.volume == 85
    assert engine.volume == 85

    controller.set_volume(150)
    assert controller.volume == 100
    assert engine.volume == 100

    controller.set_volume(-10)
    assert controller.volume == 0
    assert engine.volume == 0

def test_timeline_and_seek_dispatch():
    engine = MockAudioEngine()
    resolver = MockResolver()
    controller = PlayerController(engine=engine, resolver=resolver, db=DatabaseManager(db_path=":memory:"))

    controller.play_url("https://www.youtube.com/watch?v=test12345")
    
    # Test seeking
    controller.seek(45.5)
    assert engine.seek_position == 45.5
    assert controller.time_pos == 45.5

    # Test timeline event handling
    updates = []
    controller.add_timeline_listener(lambda pos, dur: updates.append((pos, dur)))
    controller.update_timeline(50.0, 180.0)

    assert controller.time_pos == 50.0
    assert controller.duration == 180.0
    assert updates == [(50.0, 180.0)]
