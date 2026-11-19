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
        # True after the current song was removed: the pointer then sits on the song *before* the gap,
        # so Next plays the song after the gap and Previous plays the one before it (not two back).
        self._current_removed: bool = False

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
        self._current_removed = False

    def next_track(self) -> Optional[Track]:
        """Advance to the next track based on repeat/shuffle mode."""
        if not self._tracks:
            return None
        in_gap, self._current_removed = self._current_removed, False

        if self.repeat_mode == RepeatMode.ONE and not in_gap:
            # Stay on the same track (a removed song can't be repeated, so a gap moves on)
            return self.current_track

        if self._is_shuffle:
            if self._shuffle_pos + 1 < len(self._shuffle_order):
                self._shuffle_pos += 1
            elif self.repeat_mode == RepeatMode.ALL:
                # New round: the rebuilt order starts with the song that just played, so begin at its successor.
                self._rebuild_shuffle_order()
                self._shuffle_pos = 1 if len(self._shuffle_order) > 1 else 0
            else:
                return None  # end of the shuffled order; position stays valid for Previous
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
        if self._current_removed:
            # The pointer already sits on the song before the removed one.
            self._current_removed = False
            if self.current_track is not None:
                return self.current_track

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
        self._current_removed = False
        if self._is_shuffle:
            self._rebuild_shuffle_order()
            self._shuffle_pos = 0
        return self.current_track

    def remove(self, index: int) -> Optional[Track]:
        """Remove the track at `index`. The playing song keeps playing; Next continues after it."""
        if not 0 <= index < len(self._tracks):
            return None
        removed = self._tracks.pop(index)
        if not self._tracks:
            self.load_tracks([])
            return removed
        if index == self._current_index:
            self._current_removed = True
        if index <= self._current_index:
            self._current_index -= 1
        if self._is_shuffle:
            # Keep the round going: drop the entry and renumber, instead of reshuffling played songs back in.
            removed_pos = self._shuffle_order.index(index)
            self._shuffle_order = [i - (i > index) for i in self._shuffle_order if i != index]
            if removed_pos <= self._shuffle_pos:
                self._shuffle_pos -= 1
            self._current_index = self._shuffle_order[self._shuffle_pos] if self._shuffle_pos >= 0 else -1
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
        """Build a randomized order that starts with the current track (if there is one)."""
        indices = list(range(len(self._tracks)))
        first = [self._current_index] if self._current_index in indices else []
        rest = [i for i in indices if i not in first]
        random.shuffle(rest)
        self._shuffle_order = first + rest
