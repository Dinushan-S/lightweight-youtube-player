import pytest
import time
from src.player.mpv_engine import MpvEngine

def test_mpv_engine_lifecycle():
    engine = MpvEngine(pipe_name="test_mpv_pipe")
    try:
        engine.start()
        assert engine._is_running
        assert engine._handle is not None

        # Test command sending
        engine.set_volume(50)
        time.sleep(0.05)
    finally:
        engine.stop()
        assert not engine._is_running
        assert engine._handle is None
