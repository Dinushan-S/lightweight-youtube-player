import pytest
from src.player.resolver import StreamResolver

def test_extract_audio_format_prefers_opus():
    resolver = StreamResolver()
    # Format selector should prioritize opus then m4a then bestaudio
    selector = resolver.get_format_selector()
    assert "opus" in selector
    assert "bestaudio" in selector
