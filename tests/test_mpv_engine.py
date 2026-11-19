import pytest
import os
import json
from src.player.mpv_engine import MpvEngine, find_mpv_binary

def test_find_mpv_binary():
    path = find_mpv_binary()
    assert path is not None
    assert os.path.exists(path)

def test_serialize_command():
    cmd = MpvEngine.build_command("loadfile", "https://audio.url", "replace")
    parsed = json.loads(cmd)
    assert parsed == {"command": ["loadfile", "https://audio.url", "replace"]}

def test_serialize_property():
    cmd = MpvEngine.build_property("volume", 75)
    parsed = json.loads(cmd)
    assert parsed == {"command": ["set_property", "volume", 75]}
