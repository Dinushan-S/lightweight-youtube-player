import pytest
from src.player.database import DatabaseManager
from src.player.models import Track

def test_database_record_and_fetch_history():
    db = DatabaseManager(db_path=":memory:")
    track = Track(
        video_id="vid_123",
        title="Synthwave Coding Session",
        channel="Retro Synth",
        duration_sec=320,
        stream_url="https://audio.example.com/123",
    )

    db.record_history(track)
    history = db.get_history()

    assert len(history) == 1
    assert history[0].video_id == "vid_123"
    assert history[0].title == "Synthwave Coding Session"
    assert history[0].channel == "Retro Synth"
    assert history[0].duration_sec == 320

def test_database_history_deduplication_updates_timestamp_and_count():
    db = DatabaseManager(db_path=":memory:")
    track = Track(
        video_id="vid_123",
        title="Synthwave Coding Session",
        channel="Retro Synth",
        duration_sec=320,
    )

    db.record_history(track)
    db.record_history(track)
    history = db.get_history()

    assert len(history) == 1
    row = db.get_history_row("vid_123")
    assert row["play_count"] == 2
