import threading
from dataclasses import replace
from typing import Optional, Any, Callable, List
from urllib.parse import urlparse, parse_qs
from src.player.models import PlaybackState, Track, RepeatMode
from src.player.mpv_engine import MpvEngine
from src.player.resolver import StreamResolver
from src.player.database import DatabaseManager
from src.player.queue_manager import QueueManager


def is_playlist_url(url: str) -> bool:
    """Any link carrying `list=` is a playlist; `watch?v=X&list=Y` starts it at X."""
    return "list" in parse_qs(urlparse(url).query)


class PlayerController:
    """The central orchestrator managing playback state, queue, timeline, and user commands."""

    def __init__(self, engine: Optional[Any] = None, resolver: Optional[Any] = None, db: Optional[Any] = None):
        self._engine = engine or MpvEngine()
        self._resolver = resolver or StreamResolver()
        self._db = db or DatabaseManager()
        self._queue = QueueManager()
        self._state = PlaybackState.IDLE
        self._current_track: Optional[Track] = None
        self._volume: int = 100
        self._muted: bool = False
        self._time_pos: float = 0.0
        self._duration: float = 0.0
        self._state_listeners: List[Callable[[PlaybackState, Optional[Track]], None]] = []
        self._timeline_listeners: List[Callable[[float, float], None]] = []
        self._history_listeners: List[Callable[[], None]] = []
        self._queue_listeners: List[Callable[[], None]] = []

        # If engine supports event listeners, register our event bridge
        if hasattr(self._engine, "add_event_listener"):
            self._engine.add_event_listener(self._handle_engine_event)

    @property
    def state(self) -> PlaybackState:
        return self._state

    @property
    def current_track(self) -> Optional[Track]:
        return self._current_track

    @property
    def volume(self) -> int:
        return self._volume

    @property
    def time_pos(self) -> float:
        return self._time_pos

    @property
    def duration(self) -> float:
        return self._duration

    @property
    def repeat_mode(self) -> RepeatMode:
        return self._queue.repeat_mode

    @property
    def is_shuffle(self) -> bool:
        return self._queue.is_shuffle

    @property
    def queue_tracks(self) -> List[Track]:
        return self._queue.tracks

    @property
    def queue_index(self) -> int:
        return self._queue.current_index

    def add_state_listener(self, listener: Callable[[PlaybackState, Optional[Track]], None]):
        self._state_listeners.append(listener)

    def add_timeline_listener(self, listener: Callable[[float, float], None]):
        self._timeline_listeners.append(listener)

    def add_history_listener(self, listener: Callable[[], None]):
        self._history_listeners.append(listener)

    def add_queue_listener(self, listener: Callable[[], None]):
        self._queue_listeners.append(listener)

    def _notify_history_change(self):
        for listener in self._history_listeners:
            try:
                listener()
            except Exception as e:
                print(f"[Controller History Listener Error] {e}")

    def _notify_state_change(self):
        for listener in self._state_listeners:
            try:
                listener(self._state, self._current_track)
            except Exception as e:
                print(f"[Controller State Listener Error] {e}")

    def _notify_timeline_change(self):
        for listener in self._timeline_listeners:
            try:
                listener(self._time_pos, self._duration)
            except Exception as e:
                print(f"[Controller Timeline Listener Error] {e}")

    def _notify_queue_change(self):
        for listener in self._queue_listeners:
            try:
                listener()
            except Exception as e:
                print(f"[Controller Queue Listener Error] {e}")

    def update_timeline(self, time_pos: float, duration: float):
        self._time_pos = max(0.0, time_pos)
        if duration > 0:
            self._duration = duration
        elif self._current_track and self._current_track.duration_sec > 0:
            self._duration = float(self._current_track.duration_sec)
        self._notify_timeline_change()

    def _handle_engine_event(self, event: dict):
        event_name = event.get("event")
        if event_name == "property-change":
            prop_name = event.get("name")
            data = event.get("data")
            if prop_name == "time-pos" and data is not None:
                self.update_timeline(float(data), self._duration)
            elif prop_name == "duration" and data is not None:
                self.update_timeline(self._time_pos, float(data))
        elif event_name == "pause":
            self._state = PlaybackState.PAUSED
            self._notify_state_change()
        elif event_name == "unpause":
            self._state = PlaybackState.PLAYING
            self._notify_state_change()
        elif event_name == "playback-restart" and self._state != PlaybackState.PAUSED:
            # mpv also fires this after a seek; a paused player must stay paused.
            self._state = PlaybackState.PLAYING
            self._notify_state_change()
        elif event_name == "end-file":
            reason = event.get("reason")
            if reason == "eof":
                # Only a natural end advances; "stop" is mpv replacing/stopping the file (Next, jump, Stop).
                self._auto_advance()
            elif reason == "error":
                # Load failed (e.g. expired/forbidden stream): don't sit on PLAYING at 0:00.
                self._state = PlaybackState.IDLE
                self._time_pos = 0.0
                self._notify_state_change()
                self._notify_timeline_change()

    def _auto_advance(self):
        """Auto-advance to the next track in the queue, or go IDLE if at end."""
        next_t = self._queue.next_track()
        cur = self._current_track
        if next_t is not None and cur and cur.stream_url and next_t.video_id == cur.video_id:
            # Repeating the same song: reuse its stream instead of an ~8s re-resolve.
            # ponytail: stream URLs expire after ~6h; a song looped that long ends on a load error.
            self._play_track(cur)
            self._notify_queue_change()
        elif next_t is not None:
            self._play_track(next_t)
            self._notify_queue_change()
        else:
            self._state = PlaybackState.IDLE
            self._time_pos = 0.0
            self._notify_state_change()
            self._notify_timeline_change()

    def _play_track(self, track: Track):
        """Internal: load and start playing a track, resolving its stream off-thread if needed."""
        if not track.stream_url:
            threading.Thread(target=self._resolve_then_play, args=(track,), daemon=True).start()
            return
        self.start_engine()
        self._engine.load_stream(track.stream_url)
        self._current_track = track
        self._state = PlaybackState.PLAYING
        self._time_pos = 0.0
        self._duration = float(track.duration_sec or 0)
        self._db.record_history(track)
        self._notify_state_change()
        self._notify_timeline_change()
        self._notify_history_change()

    def load_playlist(self, tracks: List[Track], start_index: int = 0, play: bool = True):
        """Load a list of tracks into the queue and (unless play=False) start playing."""
        self._queue.load_tracks(tracks, start_index=start_index)
        current = self._queue.current_track
        if current and play:
            self._play_track(current)
        self._notify_queue_change()

    def next_track(self):
        """Advance to the next track in the queue."""
        next_t = self._queue.next_track()
        if next_t is not None:
            self._play_track(next_t)
            self._notify_queue_change()

    def prev_track(self):
        """Go back to the previous track in the queue."""
        prev_t = self._queue.prev_track()
        if prev_t is not None:
            self._play_track(prev_t)
            self._notify_queue_change()

    def play_queue_index(self, index: int):
        """Play the queue track at `index` (tracklist click)."""
        track = self._queue.jump_to(index)
        if track:
            self._play_track(track)
            self._notify_queue_change()

    def set_repeat_mode(self, mode: RepeatMode):
        self._queue.repeat_mode = mode
        self._notify_queue_change()

    def _resolve_then_play(self, track: Track):
        """Worker thread: fetch the stream for a queue track that has only metadata."""
        resolved = self._resolver.resolve_track(f"https://www.youtube.com/watch?v={track.video_id}")
        if not resolved or not resolved.stream_url:
            print(f"[Controller] Could not resolve stream for {track.video_id}")
            self.stop()
            return
        # The user may have moved on while we were resolving; a stale result must not take over.
        if self._queue.current_track is track:
            # Play a copy: the queue keeps metadata only, because stream URLs expire and replays must re-resolve.
            self._play_track(replace(track, stream_url=resolved.stream_url, format_badge=resolved.format_badge))

    def toggle_shuffle(self):
        self._queue.toggle_shuffle()
        self._notify_queue_change()

    def start_engine(self):
        """Starts the underlying audio playback engine if not already running."""
        if hasattr(self._engine, "start"):
            self._engine.start()
            # Register property observers for time-pos and duration
            if hasattr(self._engine, "send_command"):
                self._engine.send_command("observe_property", 1, "time-pos")
                self._engine.send_command("observe_property", 2, "duration")
                # Stop quits mpv and a fresh one starts at 100%: re-apply the user's level.
                self._engine.send_command("set_property", "volume", self.effective_volume)

    def get_history(self, limit: int = 50) -> List[Track]:
        return self._db.get_history(limit=limit)

    def play_url(self, url: str) -> Optional[Track]:
        """Resolves stream from URL and triggers playback."""
        self.start_engine()
        track = self._resolver.resolve_track(url)
        if track and track.stream_url:
            # A single song is a one-track queue, so Repeat works and an old playlist doesn't take over at its end.
            self._queue.load_tracks([replace(track, stream_url="")])
            self._play_track(track)
            self._notify_queue_change()
            return track
        return None

    def open_url_async(self, url: str, on_complete: Optional[Callable[[bool], None]] = None):
        """Play a single video URL, or import+play a playlist URL, off the UI thread."""
        def worker():
            try:
                if is_playlist_url(url):
                    ok = self._import_playlist(url)
                else:
                    ok = self.play_url(url) is not None
            except Exception as e:
                print(f"[Controller] Failed to open {url}: {e}")
                ok = False
            if on_complete:
                on_complete(ok)

        threading.Thread(target=worker, daemon=True).start()

    def import_playlist_async(self, url: str, on_complete: Optional[Callable[[bool], None]] = None):
        """Extract a public/unlisted playlist in the background, store it, and play it from the top."""
        def worker():
            ok = self._import_playlist(url)
            if on_complete:
                on_complete(ok)

        threading.Thread(target=worker, daemon=True).start()

    def _import_playlist(self, url: str) -> bool:
        start_id = parse_qs(urlparse(url).query).get("v", [""])[0]
        # Fetching a big playlist takes ~15s: play the linked song right away while it loads.
        early: List[Optional[Track]] = []
        early_thread = None
        if start_id:
            early_thread = threading.Thread(
                target=lambda: early.append(self.play_url(f"https://www.youtube.com/watch?v={start_id}")),
                daemon=True,
            )
            early_thread.start()
        title, tracks = self._resolver.resolve_playlist(url)
        if early_thread:
            early_thread.join()
        if not tracks:
            return bool(early and early[0])
        playlist_id = parse_qs(urlparse(url).query).get("list", [url])[0]
        # Re-importing replaces the stored copy; otherwise tracks would be duplicated.
        self._db.delete_playlist(playlist_id)
        self._db.create_playlist(playlist_id, title, source_type="youtube_synced", source_url=url)
        self._db.add_playlist_tracks(playlist_id, tracks)
        start = next((i for i, t in enumerate(tracks) if t.video_id == start_id), None)
        if start is not None and early and early[0]:
            self.load_playlist(tracks, start_index=start, play=False)  # already playing it
        else:
            self.load_playlist(tracks, start_index=start or 0)
        return True

    def pause(self):
        if self._state == PlaybackState.PLAYING:
            self._engine.pause()
            self._state = PlaybackState.PAUSED
            self._notify_state_change()

    def resume(self):
        if self._state == PlaybackState.PAUSED:
            self._engine.resume()
            self._state = PlaybackState.PLAYING
            self._notify_state_change()

    def toggle_play_pause(self):
        if self._state == PlaybackState.PLAYING:
            self.pause()
        elif self._state == PlaybackState.PAUSED:
            self.resume()
        elif self._current_track and self._current_track.stream_url:
            # IDLE (track ended) or STOPPED: replay the last track; _play_track restarts mpv if Stop quit it.
            self._play_track(self._current_track)

    def seek(self, seconds: float):
        target = max(0.0, seconds)
        if self._duration > 0:
            target = min(self._duration, target)
        self._time_pos = target
        self._engine.seek(target)
        self._notify_timeline_change()

    @property
    def muted(self) -> bool:
        return self._muted

    @property
    def effective_volume(self) -> int:
        return 0 if self._muted else self._volume

    def set_volume(self, volume: int):
        """Moving the volume slider also unmutes, like every desktop player."""
        self._volume = max(0, min(100, volume))
        self._muted = False
        self._engine.set_volume(self._volume)

    def toggle_mute(self):
        """Mute keeps the chosen level so unmuting restores it."""
        self._muted = not self._muted
        self._engine.set_volume(self.effective_volume)

    def stop(self):
        # Keeps _current_track so Play after Stop restarts it.
        self._engine.stop()
        self._state = PlaybackState.STOPPED
        self._time_pos = 0.0
        self._duration = 0.0
        self._notify_state_change()
        self._notify_timeline_change()
