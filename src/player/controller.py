import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Optional, Any, Callable, List
from urllib.parse import urlparse, parse_qs
from src.player.models import PlaybackState, Track, RepeatMode
from src.player.mpv_engine import MpvEngine
from src.player.resolver import StreamResolver
from src.player.database import DatabaseManager
from src.player.google_account import GoogleAccount, SignedOut
from src.player.queue_manager import QueueManager


def is_playlist_url(url: str) -> bool:
    """Any link carrying `list=` is a playlist; `watch?v=X&list=Y` starts it at X."""
    return "list" in parse_qs(urlparse(url).query)


class PlayerController:
    """The central orchestrator managing playback state, queue, timeline, and user commands."""

    def __init__(self, engine: Optional[Any] = None, resolver: Optional[Any] = None, db: Optional[Any] = None,
                 google_client: Optional[dict] = None, google_http: Optional[Callable] = None):
        self._engine = engine or MpvEngine()
        self._resolver = resolver or StreamResolver()
        self._db = db or DatabaseManager()
        # Google account sync is only offered when a client_secret*.json was supplied
        self._google = (GoogleAccount(google_client, self._db, **({"http": google_http} if google_http else {}))
                        if google_client else None)
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
        self._favorites_listeners: List[Callable[[], None]] = []
        self._playlists_listeners: List[Callable[[], None]] = []
        self._playlist_id: Optional[str] = None  # stored playlist the queue came from, if any
        self._view = "full"  # "full" window or "mini" (docked)
        # Bumped by every pasted-link open and by Cancel: a lookup whose number is no longer current is dropped.
        self._open_seq = 0
        self._resolve_failures = 0  # consecutive queue songs that could not be resolved
        self._pending_track: Optional[Track] = None  # queue song whose stream is being fetched right now

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

    def add_favorites_listener(self, listener: Callable[[], None]):
        self._favorites_listeners.append(listener)

    def add_playlists_listener(self, listener: Callable[[], None]):
        self._playlists_listeners.append(listener)

    @staticmethod
    def _call_all(listeners: List[Callable[[], None]], name: str):
        for listener in listeners:
            try:
                listener()
            except Exception as e:
                print(f"[Controller {name} Listener Error] {e}")

    def _notify_history_change(self):
        self._call_all(self._history_listeners, "History")

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
        self._call_all(self._queue_listeners, "Queue")

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
                # If the user already picked the next song and it is still loading, that pick wins.
                if self._pending_track is None:
                    self._auto_advance()
            elif reason == "error":
                # Load failed (e.g. expired/forbidden stream): don't sit on PLAYING at 0:00.
                self._go_idle()

    def _go_idle(self):
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
            self._go_idle()

    def _play_track(self, track: Track):
        """Internal: load and start playing a track, resolving its stream off-thread if needed."""
        if not track.stream_url:
            self._pending_track = track
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
        self._playlist_id = None
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

    def remove_from_queue(self, index: int):
        """Delete a song from the queue, and from the saved playlist when the queue is one."""
        removed = self._queue.remove(index)
        if removed is None:
            return
        if self._playlist_id:
            self._db.remove_playlist_track(self._playlist_id, removed.video_id)
        self._notify_queue_change()

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self._db.get_setting(key, default)

    def set_setting(self, key: str, value: str):
        self._db.set_setting(key, value)

    def is_favorite(self, video_id: str) -> bool:
        return self._db.is_favorite(video_id)

    def get_favorites(self) -> List[Track]:
        return self._db.get_favorites()

    def set_favorite(self, track: Track, on: bool):
        self._db.set_favorite(track, on)
        self._call_all(self._favorites_listeners, "Favorites")

    # --- own playlists -------------------------------------------------------------
    @property
    def playlist_id(self) -> Optional[str]:
        """The stored playlist the queue was loaded from (edits to the queue are saved to it)."""
        return self._playlist_id

    def get_playlists(self) -> List[dict]:
        return self._db.get_playlists()

    def create_playlist(self, title: str) -> str:
        playlist_id = f"local-{uuid.uuid4().hex[:12]}"
        self._db.create_playlist(playlist_id, title.strip() or "New playlist", source_type="local")
        self._call_all(self._playlists_listeners, "Playlists")
        return playlist_id

    def rename_playlist(self, playlist_id: str, title: str):
        if title.strip():
            self._db.rename_playlist(playlist_id, title.strip())
            self._call_all(self._playlists_listeners, "Playlists")

    def delete_playlist(self, playlist_id: str):
        """The queue keeps playing; it just stops being saved to the deleted playlist."""
        self._db.delete_playlist(playlist_id)
        if self._playlist_id == playlist_id:
            self._playlist_id = None
        self._call_all(self._playlists_listeners, "Playlists")

    def add_to_playlist(self, playlist_id: str, track: Track):
        self._db.add_playlist_tracks(playlist_id, [track])
        if playlist_id == self._playlist_id:  # it's the open queue: keep queue and saved copy identical
            self._queue.append(replace(track, stream_url=""))
            self._notify_queue_change()
        self._call_all(self._playlists_listeners, "Playlists")

    def add_url_to_playlist_async(self, playlist_id: str, url: str,
                                  on_complete: Optional[Callable[[bool], None]] = None):
        """Look up a pasted song link (~5-10 s) and add it to a playlist, off the UI thread."""
        def worker():
            try:
                track = self._resolver.resolve_track(url)
                if track:
                    self.add_to_playlist(playlist_id, replace(track, stream_url=""))
                ok = track is not None
            except Exception as e:
                print(f"[Controller] Could not add {url} to playlist: {e}")
                ok = False
            if on_complete:
                on_complete(ok)

        threading.Thread(target=worker, daemon=True).start()

    def play_playlist(self, playlist_id: str) -> bool:
        tracks = self._db.get_playlist_tracks(playlist_id)
        if not tracks:
            return False
        self.load_playlist(tracks)
        self._playlist_id = playlist_id
        return True

    def move_in_queue(self, index: int, to: int):
        """Reorder the queue; saved to its playlist when the queue is one."""
        if self._queue.move(index, to):
            if self._playlist_id:
                self._db.set_playlist_tracks(self._playlist_id, self._queue.tracks)
            self._notify_queue_change()

    # --- Google account (your YouTube playlists and liked videos) ---------------------
    @property
    def google_available(self) -> bool:
        return self._google is not None

    @property
    def google_connected(self) -> bool:
        return bool(self._google and self._google.connected)

    def sync_google(self) -> int:
        """Copy the account's music into the player; returns how many playlists.

        Music only: a playlist comes in when at least half its playable videos are in YouTube's Music
        category, with just those songs; liked videos become "Liked music". Each sync replaces the
        stored copies and drops ones no longer wanted. Raises SignedOut.
        """
        g = self._google
        if not g:
            raise SignedOut("Google sign-in isn't set up")
        lists = g.playlists()
        with ThreadPoolExecutor(8) as pool:  # ~2 API calls per playlist; one at a time took minutes for 190
            fetched = list(pool.map(lambda p: g.playlist_tracks(p[0]), lists))
        wanted = [(f"google-{pid}", title, songs) for (pid, title), (songs, playable) in zip(lists, fetched)
                  if songs and 2 * len(songs) >= playable]
        liked, _ = g.liked()
        if liked:
            wanted.append(("google-LL", "Liked music", liked))  # LL = YouTube's own id for liked videos
        self._drop_google_playlists(keep={pid for pid, _, _ in wanted})
        for pid, title, tracks in wanted:
            self._db.create_playlist(pid, title, source_type="google",
                                     source_url=f"https://www.youtube.com/playlist?list={pid[7:]}")
            self._db.set_playlist_tracks(pid, tracks)
        self._call_all(self._playlists_listeners, "Playlists")
        return len(wanted)

    def _google_worker(self, sign_in: Optional[Callable[[], None]], on_complete: Optional[Callable[[bool, str], None]]):
        def worker():
            try:
                if sign_in:
                    sign_in()
                n = self.sync_google()
                ok, msg = True, f"Google: {n} playlist{'' if n == 1 else 's'} synced"
            except SignedOut as e:
                ok, msg = False, ("Google sign-in expired. Connect again." if "sign-in expired" in str(e)
                                  else f"Google sign-in didn't finish ({e})")
                self._call_all(self._playlists_listeners, "Playlists")
            except Exception as e:
                print(f"[Controller] Google sync failed: {e}")
                ok, msg = False, "Couldn't reach Google. Try again later."
            if on_complete:
                on_complete(ok, msg)

        threading.Thread(target=worker, daemon=True).start()

    def connect_google_async(self, on_code: Callable[[str, str], None],
                             on_complete: Optional[Callable[[bool, str], None]] = None,
                             on_signed_in: Optional[Callable[[], None]] = None) -> threading.Event:
        """Get a sign-in code (on_code(code, url) shows it), wait for the user to enter it
        (then on_signed_in()), then sync. Set the returned event to give up waiting.
        """
        cancel = threading.Event()

        def sign_in():
            start = self._google.start_sign_in()
            on_code(start["user_code"], start["verification_url"])
            self._google.finish_sign_in(start, cancel)
            if on_signed_in:
                on_signed_in()

        self._google_worker(sign_in, on_complete)
        return cancel

    def sync_google_async(self, on_complete: Optional[Callable[[bool, str], None]] = None):
        self._google_worker(None, on_complete)

    def disconnect_google(self):
        """Forget the sign-in and remove the synced playlists (History and Favorites stay)."""
        if self._google:
            self._google.sign_out()
        self._drop_google_playlists(keep=set())
        self._call_all(self._playlists_listeners, "Playlists")

    def _drop_google_playlists(self, keep: set):
        """Delete synced Google playlists not in `keep`, without a UI refresh per playlist (callers notify once)."""
        for p in self._db.get_playlists():
            if p["source_type"] == "google" and p["id"] not in keep:
                self._db.delete_playlist(p["id"])
                if self._playlist_id == p["id"]:
                    self._playlist_id = None

    # --- window view (full window or docked mini player) ---------------------------
    @property
    def view(self) -> str:
        return self._view

    def set_view(self, view: str):
        if view not in ("full", "mini"):
            raise ValueError(view)
        self._view = view

    @property
    def dock_pinned(self) -> bool:
        """Whether the docked mini player stays above other windows (saved; on by default)."""
        return self._db.get_setting("dock_pinned", "1") == "1"

    def set_dock_pinned(self, on: bool):
        self._db.set_setting("dock_pinned", "1" if on else "0")

    def set_repeat_mode(self, mode: RepeatMode):
        self._queue.repeat_mode = mode
        self._notify_queue_change()

    def _resolve_then_play(self, track: Track):
        """Worker thread: fetch the stream for a queue track that has only metadata."""
        try:
            resolved = self._resolver.resolve_track(f"https://www.youtube.com/watch?v={track.video_id}")
        except Exception as e:
            print(f"[Controller] Resolve crashed for {track.video_id}: {e}")
            resolved = None
        if self._pending_track is track:
            self._pending_track = None
        # The user may have moved on while we were resolving; a stale result, good or bad, must not take over.
        if self._queue.current_track is not track:
            return
        if not resolved or not resolved.stream_url:
            # Deleted/private/blocked video: skip it, but give up once every queued song has failed in a row.
            print(f"[Controller] Could not resolve stream for {track.video_id}; skipping")
            self._resolve_failures += 1
            if self._resolve_failures >= len(self._queue.tracks):
                self._resolve_failures = 0
                self._go_idle()
            else:
                self._auto_advance()
            return
        self._resolve_failures = 0
        try:
            # Play a copy: the queue keeps metadata only, because stream URLs expire and replays must re-resolve.
            self._play_track(replace(track, stream_url=resolved.stream_url, format_badge=resolved.format_badge))
        except Exception as e:  # e.g. mpv missing or its pipe failed
            print(f"[Controller] Could not start playback: {e}")
            self._go_idle()

    def toggle_shuffle(self):
        self._queue.toggle_shuffle()
        self._notify_queue_change()

    def start_engine(self):
        """Starts the underlying audio playback engine if not already running."""
        if hasattr(self._engine, "start"):
            launched = self._engine.start()
            # Only a freshly launched mpv needs these: mpv keeps every observe_property it is sent,
            # so re-sending them per track would multiply each position update.
            if launched and hasattr(self._engine, "send_command"):
                self._engine.send_command("observe_property", 1, "time-pos")
                self._engine.send_command("observe_property", 2, "duration")
                # Stop quits mpv and a fresh one starts at 100%: re-apply the user's level.
                self._engine.send_command("set_property", "volume", self.effective_volume)

    def get_history(self, limit: int = 50) -> List[Track]:
        return self._db.get_history(limit=limit)

    def play_url(self, url: str, seq: Optional[int] = None) -> Optional[Track]:
        """Resolves stream from URL and triggers playback (unless the open was cancelled or replaced meanwhile)."""
        seq = self._open_seq if seq is None else seq
        self.start_engine()
        track = self._resolver.resolve_track(url)
        if seq != self._open_seq:
            return None  # cancelled, or the user opened another link while this one was loading
        if track and track.stream_url:
            # A single song is a one-track queue, so Repeat works and an old playlist doesn't take over at its end.
            self._queue.load_tracks([replace(track, stream_url="")])
            self._playlist_id = None
            self._play_track(track)
            self._notify_queue_change()
            return track
        return None

    def open_url_async(self, url: str, on_complete: Optional[Callable[[bool], None]] = None):
        """Play a single video URL, or import+play a playlist URL, off the UI thread.

        Replaces any open still loading: that one's result is dropped when its lookup finishes.
        """
        self._open_seq += 1
        seq = self._open_seq

        def worker():
            try:
                if is_playlist_url(url):
                    ok = self._import_playlist(url, seq)
                else:
                    ok = self.play_url(url, seq) is not None
            except Exception as e:
                print(f"[Controller] Failed to open {url}: {e}")
                ok = False
            if on_complete:
                on_complete(ok)

        threading.Thread(target=worker, daemon=True).start()

    def cancel_open(self):
        """Stop waiting for the link being opened (yt-dlp can't be interrupted, so its result is dropped)."""
        self._open_seq += 1

    def import_playlist_async(self, url: str, on_complete: Optional[Callable[[bool], None]] = None):
        """Extract a public/unlisted playlist in the background, store it, and play it."""
        self.open_url_async(url, on_complete)  # same guarded worker; playlist links route to _import_playlist

    def _import_playlist(self, url: str, seq: Optional[int] = None) -> bool:
        seq = self._open_seq if seq is None else seq
        start_id = parse_qs(urlparse(url).query).get("v", [""])[0]
        # Fetching a big playlist takes ~15s: play the linked song right away while it loads.
        early: List[Optional[Track]] = []
        early_thread = None
        if start_id:
            early_thread = threading.Thread(
                target=lambda: early.append(self.play_url(f"https://www.youtube.com/watch?v={start_id}", seq)),
                daemon=True,
            )
            early_thread.start()
        title, tracks = self._resolver.resolve_playlist(url)
        if early_thread:
            early_thread.join()
        if seq != self._open_seq:
            return False  # cancelled or replaced: don't store it or take over the queue
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
        self._playlist_id = playlist_id
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
        elif self._current_track:
            # IDLE (ended, failed, or long idle) or STOPPED: replay the last song from a fresh stream link,
            # because the cached one may be the link that just failed or may have expired (~6 h).
            # Queue entries hold metadata only, so playing the queue entry re-resolves it.
            queued = self._queue.current_track
            if queued is not None and queued.video_id == self._current_track.video_id:
                self._play_track(queued)
            else:
                url = f"https://www.youtube.com/watch?v={self._current_track.video_id}"
                threading.Thread(target=self.play_url, args=(url,), daemon=True).start()
        else:
            # Nothing loaded yet (media key / tray before anything played): pick up the last History song.
            last = self._db.get_history(limit=1)
            if last:
                url = f"https://www.youtube.com/watch?v={last[0].video_id}"
                threading.Thread(target=self.play_url, args=(url,), daemon=True).start()

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
