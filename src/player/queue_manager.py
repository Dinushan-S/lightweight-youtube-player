import random
from typing import List, Optional
from src.player.models import Track, RepeatMode


class QueueManager:
    """Manages the playback queue: track list, navigation, shuffle, and repeat modes."""

    def __init__(self):
        self._tracks: List[Track] = []
        self._current_index: int = -1
        self.repeat_mode: RepeatMode = RepeatMode.OFF
        self._is_shuffle: bool = False
        self._shuffle_order: List[int] = []
        self._shuffle_pos: int = -1

    @property
    def tracks(self) -> List[Track]:
        return list(self._tracks)

    @property
    def is_shuffle(self) -> bool:
        return self._is_shuffle

    @property
    def current_track(self) -> Optional[Track]:
        if 0 <= self._current_index < len(self._tracks):
            return self._tracks[self._current_index]
        return None

    @property
    def current_index(self) -> int:
        return self._current_index

    def load_tracks(self, tracks: List[Track], start_index: int = 0):
        """Load a list of tracks into the queue and set the starting position."""
        self._tracks = list(tracks)
        self._current_index = start_index if tracks else -1
        self._is_shuffle = False
        self._shuffle_order = []
        self._shuffle_pos = -1

    def next_track(self) -> Optional[Track]:
        """Advance to the next track based on repeat/shuffle mode."""
        if not self._tracks:
            return None

        if self.repeat_mode == RepeatMode.ONE:
            # Stay on the same track
            return self.current_track

        if self._is_shuffle:
            self._shuffle_pos += 1
            if self._shuffle_pos >= len(self._shuffle_order):
                if self.repeat_mode == RepeatMode.ALL:
                    self._rebuild_shuffle_order()
                    self._shuffle_pos = 0
                else:
                    return None
            self._current_index = self._shuffle_order[self._shuffle_pos]
            return self.current_track

        # Normal sequential
        next_idx = self._current_index + 1
        if next_idx >= len(self._tracks):
            if self.repeat_mode == RepeatMode.ALL:
                next_idx = 0
            else:
                return None

        self._current_index = next_idx
        return self.current_track

    def prev_track(self) -> Optional[Track]:
        """Go back to the previous track."""
        if not self._tracks:
            return None

        if self._is_shuffle:
            if self._shuffle_pos > 0:
                self._shuffle_pos -= 1
                self._current_index = self._shuffle_order[self._shuffle_pos]
            return self.current_track

        prev_idx = self._current_index - 1
        if prev_idx < 0:
            if self.repeat_mode == RepeatMode.ALL:
                prev_idx = len(self._tracks) - 1
            else:
                return self.current_track
        self._current_index = prev_idx
        return self.current_track

    def jump_to(self, index: int) -> Optional[Track]:
        """Make the track at `index` current (e.g. a click in the tracklist)."""
        if not 0 <= index < len(self._tracks):
            return None
        self._current_index = index
        if self._is_shuffle:
            self._rebuild_shuffle_order()
            self._shuffle_pos = 0
        return self.current_track

    def remove(self, index: int) -> Optional[Track]:
        """Remove the track at `index`. The playing song keeps playing; Next continues after it."""
        if not 0 <= index < len(self._tracks):
            return None
        removed = self._tracks.pop(index)
        if index <= self._current_index:
            # Removing the current song steps back one, so next_track() lands on the song that slid into its place.
            self._current_index -= 1
        if not self._tracks:
            self._current_index = -1
        if self._is_shuffle:
            self._rebuild_shuffle_order()
            self._shuffle_pos = 0
        return removed

    def toggle_shuffle(self):
        """Toggle shuffle mode on/off. When enabled, shuffles remaining tracks keeping current track."""
        self._is_shuffle = not self._is_shuffle
        if self._is_shuffle:
            self._rebuild_shuffle_order()
            # Position in shuffle starts at 0 (current track is first in shuffle order)
            self._shuffle_pos = 0
        else:
            self._shuffle_order = []
            self._shuffle_pos = -1

    def _rebuild_shuffle_order(self):
        """Build a randomized order that starts with the current track."""
        indices = list(range(len(self._tracks)))
        if self._current_index in indices:
            indices.remove(self._current_index)
        random.shuffle(indices)
        self._shuffle_order = [self._current_index] + indices
