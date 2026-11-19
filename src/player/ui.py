import threading
import customtkinter as ctk
from typing import Optional, List
from src.player.controller import PlayerController, is_playlist_url
from src.player.models import PlaybackState, RepeatMode, Track

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

def format_time(seconds: float) -> str:
    total_sec = int(max(0, seconds))
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    secs = total_sec % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

class MusicPlayerApp(ctk.CTk):
    """Minimal, ultra-lightweight YouTube Music Player UI."""

    COLOR_BG = "#0b0f17"
    COLOR_CARD = "#161f30"
    COLOR_CARD_HOVER = "#222f46"
    COLOR_ACCENT = "#38bdf8"
    COLOR_ACCENT_HOVER = "#0284c7"
    COLOR_TEXT = "#f8fafc"
    COLOR_TEXT_MUTED = "#94a3b8"
    QUEUE_WINDOW = 60
    ICON_FONT = "Segoe UI Symbol"  # monochrome media glyphs; plain Segoe UI falls back to colour emoji

    def __init__(self, controller: Optional[PlayerController] = None):
        super().__init__()
        self.controller = controller or PlayerController()
        self._is_seeking = False
        self._cached_history: List[Track] = []

        # Window Setup
        self.title("Lightweight YouTube Player")
        self.geometry("840x520")
        self.minsize(640, 400)
        self.configure(fg_color=self.COLOR_BG)

        # Build UI layout
        self._build_widgets()

        # Register controller listeners
        self.controller.add_state_listener(self._on_player_state_change)
        self.controller.add_timeline_listener(self._on_timeline_update)
        self.controller.add_history_listener(self._refresh_history_ui)
        self.controller.add_queue_listener(self._on_queue_change)

        # Load initial history
        self._refresh_history_ui()

        # Window closing handler
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_widgets(self):
        # Header / Input Frame
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=20, pady=(15, 8))

        self.url_entry = ctk.CTkEntry(
            self.header_frame,
            placeholder_text="Paste YouTube video or playlist link...",
            height=38,
            fg_color=self.COLOR_CARD,
            border_color="#1e293b",
            text_color=self.COLOR_TEXT,
            placeholder_text_color=self.COLOR_TEXT_MUTED,
            font=("Segoe UI", 13),
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.url_entry.bind("<Return>", lambda e: self._on_play_click())

        self.play_url_btn = ctk.CTkButton(
            self.header_frame,
            text="▶ Play",
            width=90,
            height=38,
            fg_color=self.COLOR_ACCENT,
            hover_color=self.COLOR_ACCENT_HOVER,
            text_color="#0b0f17",
            font=("Segoe UI", 13, "bold"),
            command=self._on_play_click,
        )
        self.play_url_btn.pack(side="right")

        # Main Content Split (Now Playing Left, History Right)
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=20, pady=(5, 15))

        # Left: Now Playing Card
        self.card_frame = ctk.CTkFrame(
            self.content_frame,
            fg_color=self.COLOR_CARD,
            corner_radius=12,
            border_width=1,
            border_color="#1e293b",
        )
        self.card_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.status_label = ctk.CTkLabel(
            self.card_frame,
            text="IDLE",
            font=("Segoe UI", 11, "bold"),
            text_color=self.COLOR_ACCENT,
        )
        self.status_label.pack(anchor="w", padx=20, pady=(15, 4))

        self.title_label = ctk.CTkLabel(
            self.card_frame,
            text="Paste a YouTube link above to start listening",
            font=("Segoe UI", 16, "bold"),
            text_color=self.COLOR_TEXT,
            anchor="w",
            wraplength=400,
        )
        self.title_label.pack(anchor="w", padx=20, pady=(0, 4))

        self.channel_label = ctk.CTkLabel(
            self.card_frame,
            text="Audio-Only Stream • Zero Video Decoding",
            font=("Segoe UI", 12),
            text_color=self.COLOR_TEXT_MUTED,
            anchor="w",
        )
        self.channel_label.pack(anchor="w", padx=20, pady=(0, 8))

        self.badge_label = ctk.CTkLabel(
            self.card_frame,
            text="⚡ Highest Quality Opus 160k",
            font=("Segoe UI", 10, "bold"),
            text_color="#38bdf8",
            fg_color="#0f2438",
            corner_radius=6,
            padx=8,
            pady=2,
        )
        self.badge_label.pack(anchor="w", padx=20, pady=(0, 15))

        # Timeline Frame inside Now Playing
        self.timeline_frame = ctk.CTkFrame(self.card_frame, fg_color="transparent")
        self.timeline_frame.pack(fill="x", padx=20, pady=(5, 10))

        self.time_elapsed_label = ctk.CTkLabel(
            self.timeline_frame,
            text="00:00",
            font=("Segoe UI", 11, "bold"),
            text_color=self.COLOR_TEXT_MUTED,
            width=42,
        )
        self.time_elapsed_label.pack(side="left")

        self.seek_slider = ctk.CTkSlider(
            self.timeline_frame,
            from_=0,
            to=100,
            height=14,
            progress_color=self.COLOR_ACCENT,
            button_color=self.COLOR_ACCENT,
            button_hover_color=self.COLOR_ACCENT_HOVER,
            command=self._on_seek_drag,
        )
        self.seek_slider.set(0)
        self.seek_slider.pack(side="left", fill="x", expand=True, padx=10)
        self.seek_slider.bind("<ButtonRelease-1>", self._on_seek_release)

        self.time_total_label = ctk.CTkLabel(
            self.timeline_frame,
            text="00:00",
            font=("Segoe UI", 11, "bold"),
            text_color=self.COLOR_TEXT_MUTED,
            width=42,
        )
        self.time_total_label.pack(side="right")

        # Right: fixed-width card with History and Tracklist tabs
        side_frame = ctk.CTkFrame(
            self.content_frame,
            fg_color=self.COLOR_CARD,
            corner_radius=12,
            border_width=1,
            border_color="#1e293b",
            width=320,
        )
        side_frame.pack(side="right", fill="both", expand=False)
        side_frame.pack_propagate(False)

        self.tabs = ctk.CTkTabview(side_frame, fg_color="transparent")
        self.tabs.pack(fill="both", expand=True, padx=6, pady=6)
        self.history_frame = self.tabs.add("History")
        queue_tab = self.tabs.add("Tracklist")

        self.queue_scroll = ctk.CTkScrollableFrame(
            queue_tab,
            fg_color="transparent",
            scrollbar_button_color="#1e293b",
            scrollbar_button_hover_color=self.COLOR_CARD_HOVER,
        )
        self.queue_scroll.pack(fill="both", expand=True)

        # History Header with Search
        self.hist_header = ctk.CTkFrame(self.history_frame, fg_color="transparent")
        self.hist_header.pack(fill="x", padx=12, pady=(12, 6))

        self.hist_title = ctk.CTkLabel(
            self.hist_header,
            text="🕒 Recent History",
            font=("Segoe UI", 13, "bold"),
            text_color=self.COLOR_TEXT,
        )
        self.hist_title.pack(side="left")

        self.hist_search = ctk.CTkEntry(
            self.history_frame,
            placeholder_text="Search history...",
            height=28,
            fg_color="#0b0f17",
            border_color="#1e293b",
            text_color=self.COLOR_TEXT,
            placeholder_text_color=self.COLOR_TEXT_MUTED,
            font=("Segoe UI", 11),
        )
        self.hist_search.pack(fill="x", padx=12, pady=(0, 8))
        self.hist_search.bind("<KeyRelease>", lambda e: self._filter_history_ui())

        # History Scrollable List
        self.history_scroll = ctk.CTkScrollableFrame(
            self.history_frame,
            fg_color="transparent",
            scrollbar_button_color="#1e293b",
            scrollbar_button_hover_color=self.COLOR_CARD_HOVER,
        )
        self.history_scroll.pack(fill="both", expand=True, padx=6, pady=(0, 10))

        # Transport row, centred under the seek bar
        transport = ctk.CTkFrame(self.card_frame, fg_color="transparent")
        transport.pack(pady=(4, 6))
        self.shuffle_btn = self._icon_btn(transport, "🔀", self._on_shuffle_click, muted=True)
        self.prev_btn = self._icon_btn(transport, "⏮", self._on_prev_click)
        self.toggle_btn = self._icon_btn(transport, "▶", self._on_toggle_play_pause, size=52, font_size=20)
        self.toggle_btn.configure(fg_color=self.COLOR_ACCENT, hover_color=self.COLOR_ACCENT_HOVER, text_color=self.COLOR_BG)
        self.stop_btn = self._icon_btn(transport, "⏹", self._on_stop_click)
        self.next_btn = self._icon_btn(transport, "⏭", self._on_next_click)
        self.repeat_btn = self._icon_btn(transport, "🔁", self._on_repeat_click, muted=True)

        # Volume row: mute toggle, slider (mouse wheel = ±5), level readout
        volume_row = ctk.CTkFrame(self.card_frame, fg_color="transparent")
        volume_row.pack(pady=(0, 15))
        self.mute_btn = self._icon_btn(volume_row, "🔊", self._on_mute_click, size=32, font_size=14)
        self.volume_slider = ctk.CTkSlider(
            volume_row,
            from_=0,
            to=100,
            number_of_steps=100,
            width=160,
            progress_color=self.COLOR_ACCENT,
            button_color=self.COLOR_ACCENT,
            button_hover_color=self.COLOR_ACCENT_HOVER,
            command=self._on_volume_change,
        )
        self.volume_slider.set(self.controller.volume)
        self.volume_slider.pack(side="left", padx=(4, 8))
        self.volume_slider.bind("<MouseWheel>", lambda e: self._on_volume_change(self.controller.volume + (5 if e.delta > 0 else -5)))
        self.vol_pct_label = ctk.CTkLabel(
            volume_row,
            text="",
            width=48,
            anchor="w",
            font=("Segoe UI", 11, "bold"),
            text_color=self.COLOR_TEXT_MUTED,
        )
        self.vol_pct_label.pack(side="left")
        self._refresh_volume_ui()

    def _icon_btn(self, parent, text, command, size=40, font_size=16, muted=False):
        btn = ctk.CTkButton(
            parent,
            text=text,
            width=size,
            height=size,
            corner_radius=size // 2,
            fg_color="transparent",
            hover_color=self.COLOR_CARD_HOVER,
            text_color=self.COLOR_TEXT_MUTED if muted else self.COLOR_TEXT,
            font=(self.ICON_FONT, font_size),
            command=command,
        )
        btn.pack(side="left", padx=4)
        return btn

    def _on_play_click(self):
        if self.play_url_btn.cget("state") == "disabled":
            return  # already resolving a link
        url = self.url_entry.get().strip()
        if not url:
            # Nothing pasted: resume where the user left off.
            last = self.controller.get_history(limit=1)
            if not last:
                return
            self._play_from_history(last[0])
            return

        self.play_url_btn.configure(state="disabled", text="Loading...")
        self.status_label.configure(text="RESOLVING AUDIO STREAM...")
        if is_playlist_url(url):
            self.tabs.set("Tracklist")

        def on_done(ok: bool):
            def update_ui():
                self.play_url_btn.configure(state="normal", text="▶ Play")
                if not ok:
                    self.status_label.configure(text="ERROR: FAILED TO EXTRACT STREAM")
            self.after(0, update_ui)

        self.controller.open_url_async(url, on_complete=on_done)

    def _on_toggle_play_pause(self):
        if self.controller.current_track is None:
            self._on_play_click()  # nothing loaded yet: pasted link, else last history song
        else:
            self.controller.toggle_play_pause()

    def _on_stop_click(self):
        self.controller.stop()

    def _on_prev_click(self):
        self.controller.prev_track()

    def _on_next_click(self):
        self.controller.next_track()

    def _on_shuffle_click(self):
        self.controller.toggle_shuffle()

    def _on_repeat_click(self):
        cycle = [RepeatMode.OFF, RepeatMode.ALL, RepeatMode.ONE]
        self.controller.set_repeat_mode(cycle[(cycle.index(self.controller.repeat_mode) + 1) % len(cycle)])

    def _on_queue_change(self):
        self.after(0, self._render_queue)

    def _render_queue(self):
        for widget in self.queue_scroll.winfo_children():
            widget.destroy()

        tracks = self.controller.queue_tracks
        if not tracks:
            ctk.CTkLabel(
                self.queue_scroll,
                text="Paste a playlist link to load its tracks",
                font=("Segoe UI", 11),
                text_color=self.COLOR_TEXT_MUTED,
            ).pack(pady=20)

        active = self.controller.queue_index
        # Big playlists (1000+ songs) freeze Tk if every row is a widget: render a window around the active track.
        first = max(0, active - 5)
        shown = tracks[first:first + self.QUEUE_WINDOW]
        for i, track in enumerate(shown, start=first):
            is_active = i == active
            row = ctk.CTkFrame(
                self.queue_scroll,
                fg_color="#0f2438" if is_active else "#0f172a",
                corner_radius=8,
                cursor="hand2",
            )
            row.pack(fill="x", pady=2, padx=2)

            title = ctk.CTkLabel(
                row,
                text=f"{i + 1}. {track.title}",
                font=("Segoe UI", 12, "bold" if is_active else "normal"),
                text_color=self.COLOR_ACCENT if is_active else self.COLOR_TEXT,
                anchor="w",
            )
            title.pack(fill="x", padx=10, pady=(6, 0))

            meta = ctk.CTkLabel(
                row,
                text=f"{track.channel} • {format_time(track.duration_sec)}",
                font=("Segoe UI", 10),
                text_color=self.COLOR_TEXT_MUTED,
                anchor="w",
            )
            meta.pack(fill="x", padx=10, pady=(0, 6))

            for w in (row, title, meta):
                w.bind("<Button-1>", lambda e, idx=i: self.controller.play_queue_index(idx))

        if len(tracks) > len(shown):
            ctk.CTkLabel(
                self.queue_scroll,
                text=f"Showing {first + 1}-{first + len(shown)} of {len(tracks)}",
                font=("Segoe UI", 10),
                text_color=self.COLOR_TEXT_MUTED,
            ).pack(pady=8)

        self.shuffle_btn.configure(
            text_color=self.COLOR_ACCENT if self.controller.is_shuffle else self.COLOR_TEXT_MUTED,
        )
        repeat = self.controller.repeat_mode
        self.repeat_btn.configure(
            text="🔂" if repeat == RepeatMode.ONE else "🔁",
            text_color=self.COLOR_TEXT_MUTED if repeat == RepeatMode.OFF else self.COLOR_ACCENT,
        )

    def _on_volume_change(self, val):
        self.controller.set_volume(int(val))
        self.volume_slider.set(self.controller.volume)  # mouse-wheel path doesn't move the slider itself
        self._refresh_volume_ui()

    def _on_mute_click(self):
        self.controller.toggle_mute()
        self._refresh_volume_ui()

    def _refresh_volume_ui(self):
        vol, muted = self.controller.volume, self.controller.muted
        icon = "🔇" if muted or vol == 0 else ("🔉" if vol < 50 else "🔊")
        self.mute_btn.configure(text=icon, text_color=self.COLOR_ACCENT if muted else self.COLOR_TEXT)
        self.vol_pct_label.configure(text="Muted" if muted else f"{vol}%")

    def _on_seek_drag(self, val):
        self._is_seeking = True
        self.time_elapsed_label.configure(text=format_time(val))

    def _on_seek_release(self, event):
        val = self.seek_slider.get()
        self.controller.seek(float(val))
        self._is_seeking = False

    def _on_timeline_update(self, time_pos: float, duration: float):
        def update():
            if not self._is_seeking:
                self.time_elapsed_label.configure(text=format_time(time_pos))
                self.time_total_label.configure(text=format_time(duration))
                if duration > 0:
                    self.seek_slider.configure(to=duration)
                    self.seek_slider.set(min(time_pos, duration))
                else:
                    self.seek_slider.set(0)

        self.after(0, update)

    def _on_player_state_change(self, state: PlaybackState, track: Optional[Track]):
        def update():
            if state == PlaybackState.PLAYING:
                self.toggle_btn.configure(text="⏸")
                self.status_label.configure(text="PLAYING")
            elif state == PlaybackState.PAUSED:
                self.toggle_btn.configure(text="▶")
                self.status_label.configure(text="PAUSED")
            else:
                self.toggle_btn.configure(text="▶")
                self.status_label.configure(text=state.value)  # IDLE or STOPPED

            if track:
                self.title_label.configure(text=track.title)
                self.channel_label.configure(text=track.channel)
                self.badge_label.configure(text=f"⚡ {track.format_badge} (Audio-Only)")
                if track.duration_sec > 0:
                    self.time_total_label.configure(text=format_time(track.duration_sec))
                    self.seek_slider.configure(to=track.duration_sec)

        self.after(0, update)

    def _refresh_history_ui(self):
        def update():
            self._cached_history = self.controller.get_history()
            self._render_history_items(self._cached_history)
        self.after(0, update)

    def _filter_history_ui(self):
        query = self.hist_search.get().strip().lower()
        if not query:
            self._render_history_items(self._cached_history)
        else:
            filtered = [
                t for t in self._cached_history
                if query in t.title.lower() or query in t.channel.lower()
            ]
            self._render_history_items(filtered)

    def _render_history_items(self, tracks: List[Track]):
        for widget in self.history_scroll.winfo_children():
            widget.destroy()

        if not tracks:
            empty_lbl = ctk.CTkLabel(
                self.history_scroll,
                text="No tracks played yet",
                font=("Segoe UI", 11),
                text_color=self.COLOR_TEXT_MUTED,
            )
            empty_lbl.pack(pady=20)
            return

        for track in tracks:
            item_frame = ctk.CTkFrame(
                self.history_scroll,
                fg_color="#0f172a",
                corner_radius=8,
                cursor="hand2",
            )
            item_frame.pack(fill="x", pady=3, padx=2)

            t_lbl = ctk.CTkLabel(
                item_frame,
                text=track.title,
                font=("Segoe UI", 12, "bold"),
                text_color=self.COLOR_TEXT,
                anchor="w",
            )
            t_lbl.pack(fill="x", padx=10, pady=(6, 2))

            meta_text = f"{track.channel} • {format_time(track.duration_sec)}"
            m_lbl = ctk.CTkLabel(
                item_frame,
                text=meta_text,
                font=("Segoe UI", 10),
                text_color=self.COLOR_TEXT_MUTED,
                anchor="w",
            )
            m_lbl.pack(fill="x", padx=10, pady=(0, 6))

            # Click item to replay track
            for w in (item_frame, t_lbl, m_lbl):
                w.bind("<Button-1>", lambda e, t=track: self._play_from_history(t))

    def _play_from_history(self, track: Track):
        # The saved stream URL expires within hours; the watch link always re-resolves.
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, f"https://www.youtube.com/watch?v={track.video_id}")
        self._on_play_click()

    def _on_close(self):
        self.controller.stop()
        self.destroy()

if __name__ == "__main__":
    app = MusicPlayerApp()
    app.mainloop()
