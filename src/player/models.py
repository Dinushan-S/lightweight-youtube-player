from dataclasses import dataclass
from enum import Enum
from typing import Optional

class PlaybackState(str, Enum):
    IDLE = "IDLE"
    PLAYING = "PLAYING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"

class RepeatMode(str, Enum):
    OFF = "OFF"
    ALL = "ALL"
    ONE = "ONE"

@dataclass
class Track:
    video_id: str
    title: str
    channel: str
    duration_sec: int
    stream_url: Optional[str] = None
    format_badge: str = "Opus 160k"
    thumbnail_url: Optional[str] = None
