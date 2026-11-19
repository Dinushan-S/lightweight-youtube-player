import customtkinter as ctk
from src.player.models import PlaybackState
from src.player.ui import format_time, Icon


class MiniPlayer(ctk.CTkToplevel):
    """Docked mini player pinned to the top edge of the screen.

    Collapsed: a thin progress line. Hover: drops down with cover, title, Prev/Play/Next
    and a playlist dropdown. Mouse away: collapses again. Drag the cover/title to slide it along the top.
    """

    WIDTH = 320       # logical px
    LINE_HEIGHT = 6   # collapsed progress line
    LIST_ROWS = 30    # playlist dropdown shows this many songs around the current one

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.c = app.controller
        self._list_open = False
        self._list_key = None
        self._shown_thumb = None
        t = app.t
        self._drag_dx = None

        self.overrideredirect(True)  # no title bar
        self.attributes("-topmost", True)
        self.configure(fg_color=t["surface"])

        # Always visible: the progress line
        self.line = ctk.CTkProgressBar(
            self, width=self.WIDTH, height=self.LINE_HEIGHT, corner_radius=0,
            progress_color=t["accent"], fg_color=t["track"],
        )
        self.line.set(0)
        self.line.pack(side="bottom", fill="x")

        # Shown on hover
        self.panel = ctk.CTkFrame(self, fg_color="transparent")
        header = ctk.CTkFrame(self.panel, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(10, 4))
        self.cover = ctk.CTkLabel(
            header, text=Icon.MUSIC, width=64, height=36, corner_radius=min(t["radius"], 6),
            fg_color=t["raised"], text_color=t["muted"], font=(app.ICON_FONT, 14),
        )
        self.cover.pack(side="left")
        info = ctk.CTkFrame(header, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, padx=8)
        self.title_label = app._label(info, size=12, bold=True, anchor="w")
        self.title_label.pack(fill="x")
        self.channel_label = app._label(info, size=10, muted=True, anchor="w")
        self.channel_label.pack(fill="x")
        app._icon_btn(header, Icon.RESTORE, self._restore, size=28, font_size=12, muted=True)
        for w in (header, self.cover, info, self.title_label, self.channel_label):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag_dx", None))
            w.configure(cursor="fleur")

        # One compact row: ⏮ ⏸ ⏭  🔊 ─── volume  ·  Playlist ▾  (time sits under the title)
        controls = ctk.CTkFrame(self.panel, fg_color="transparent")
        controls.pack(fill="x", padx=6, pady=(0, 8))
        app._icon_btn(controls, Icon.PREV, self.c.prev_track, size=34, font_size=13)
        self.toggle_btn = app._icon_btn(controls, Icon.PLAY, app._on_toggle_play_pause, size=34, font_size=13)
        self.toggle_btn.configure(fg_color=t["accent"], hover_color=t["accent_hover"], text_color=t["on_accent"])
        app._icon_btn(controls, Icon.NEXT, self.c.next_track, size=34, font_size=13)
        self.fav_btn = app._icon_btn(controls, Icon.HEART, app.toggle_favorite, size=28, font_size=12, muted=True)
        self.mute_btn = app._icon_btn(controls, Icon.VOLUME_3, app._on_mute_click, size=28, font_size=12)
        self.list_btn = ctk.CTkButton(
            controls, text="Playlist", width=76, height=28, corner_radius=14,
            fg_color=t["raised"], hover_color=t["hover"], text_color=t["text"],
            font=(app.FONT, 11), command=self._toggle_list,
        )
        self.list_btn.pack(side="right", padx=4)

        # Volume bar: hidden until the mouse is over the 🔊 icon, then shown just below it.
        # Shares the main window's handlers, so both windows stay in sync.
        self.vol_row = ctk.CTkFrame(self.panel, fg_color="transparent")
        self.volume_slider = app._slider(self.vol_row, from_=0, to=100, number_of_steps=100, width=120, height=14,
                                         command=app._on_volume_change)
        self.volume_slider.pack(side="left")
        self.volume_slider.bind("<MouseWheel>", app.on_volume_wheel)  # works once the dock has focus (after a click)
        self.vol_label = app._label(self.vol_row, size=10, bold=True, muted=True, width=44)
        self.vol_label.pack(side="left", padx=(6, 0))
        self.mute_btn.bind("<Enter>", lambda e: self._show_volume())
        for w in (self.mute_btn, self.vol_row, self.volume_slider, self.vol_label):
            w.bind("<Leave>", lambda e: self.after(300, self._hide_volume_if_away), add="+")

        self.list_frame = ctk.CTkScrollableFrame(self.panel, height=220, fg_color=t["raised"],
                                                 corner_radius=min(t["radius"], 10),
                                                 scrollbar_button_color=t["track"], scrollbar_button_hover_color=t["hover"])

        self.bind("<Enter>", lambda e: self._expand())
        self.bind("<Leave>", lambda e: self.after(250, self._collapse_if_outside))

        self.update_idletasks()
        x = self.winfo_screenwidth() - self.winfo_reqwidth() - 24  # top-right corner by default
        self.geometry(f"+{x}+0")
        self._tick()

    # --- hover ---------------------------------------------------------------
    def _expand(self):
        if not self.panel.winfo_ismapped():
            self.panel.pack(side="top", fill="both")
            self._refresh()

    def _collapse_if_outside(self):
        if self._drag_dx is not None or not self.winfo_exists():
            return
        if self._pointer_over(self):
            return  # Leave fired because the mouse moved onto a child widget
        self.panel.pack_forget()
        self.vol_row.pack_forget()
        if self._list_open:
            self._toggle_list()

    # --- volume popup ------------------------------------------------------------
    def _show_volume(self):
        if not self.vol_row.winfo_ismapped():
            # line the bar up under the icon
            px = self.mute_btn.winfo_rootx() - self.panel.winfo_rootx() - 40  # screen px
            x = max(0, round(px / self.vol_row._get_widget_scaling()))  # CTk scales padx itself
            self.vol_row.pack(after=self.mute_btn.master, fill="x", padx=(x, 0), pady=(0, 8))
            self._refresh()

    def _hide_volume_if_away(self):
        if self.winfo_exists() and not self._pointer_over(self.mute_btn, self.vol_row):
            self.vol_row.pack_forget()

    @staticmethod
    def _pointer_over(*widgets):
        for w in widgets:
            if w.winfo_ismapped():
                px, py = w.winfo_pointerxy()
                x, y = w.winfo_rootx(), w.winfo_rooty()
                if x <= px < x + w.winfo_width() and y <= py < y + w.winfo_height():
                    return True
        return False

    # --- drag along the top edge ----------------------------------------------
    def _drag_start(self, event):
        self._drag_dx = event.x_root - self.winfo_rootx()

    def _drag_move(self, event):
        if self._drag_dx is None:
            return
        # ponytail: clamped to the primary screen; multi-monitor would need the virtual-root width
        x = max(0, min(event.x_root - self._drag_dx, self.winfo_screenwidth() - self.winfo_width()))
        self.geometry(f"+{x}+0")

    # --- playlist dropdown ---------------------------------------------------------
    def _toggle_list(self):
        self._list_open = not self._list_open
        if self._list_open:
            self.list_frame.pack(fill="x", padx=8, pady=(0, 8))
            self._list_key = None
            self._render_list()
        else:
            self.list_frame.pack_forget()
        self.list_btn.configure(fg_color=self.app.t["active_row"] if self._list_open else self.app.t["raised"])

    def _render_list(self):
        tracks, active = self.c.queue_tracks, self.c.queue_index
        key = (len(tracks), active)
        if key == self._list_key:
            return
        self._list_key = key
        for w in self.list_frame.winfo_children():
            w.destroy()
        if not tracks:
            self.app._label(self.list_frame, "No playlist loaded", size=11, muted=True).pack(pady=12)
            return
        first = max(0, active - 3)
        th = self.app.t
        for i, t in enumerate(tracks[first:first + self.LIST_ROWS], start=first):
            ctk.CTkButton(
                self.list_frame, text=f"{i + 1}. {self._short(t.title, 40)}", anchor="w", height=26,
                fg_color=th["active_row"] if i == active else "transparent", hover_color=th["hover"],
                text_color=th["accent"] if i == active else th["text"],
                font=(self.app.FONT, 11, "bold" if i == active else "normal"),
                command=lambda i=i: self.c.play_queue_index(i),
            ).pack(fill="x")

    # --- live updates (polled: controller callbacks come from worker threads) ----
    def _tick(self):
        if not self.winfo_exists():
            return
        dur = self.c.duration
        self.line.set(min(1.0, self.c.time_pos / dur) if dur > 0 else 0)
        if self.panel.winfo_ismapped():
            self._refresh()
        self.after(250, self._tick)

    def _refresh(self):
        t = self.c.current_track
        self.title_label.configure(text=self._short(t.title, 34) if t else "Nothing playing")
        self.channel_label.configure(
            text=f"{self._short(t.channel, 22)}  ·  {format_time(self.c.time_pos)} / {format_time(self.c.duration)}"
            if t else "Hover here any time"
        )
        self.toggle_btn.configure(text=Icon.PAUSE if self.c.state == PlaybackState.PLAYING else Icon.PLAY)
        self.volume_slider.set(self.c.volume)
        self.mute_btn.configure(text=self.app.volume_icon(),
                                text_color=self.app.t["accent"] if self.c.muted else self.app.t["text"])
        # The heart mirrors the main window's, which follows every favorites change
        self.fav_btn.configure(text=self.app.fav_btn.cget("text"), text_color=self.app.fav_btn.cget("text_color"))
        self.vol_label.configure(text=self.app.volume_text())
        if t:
            self._show_cover(t.video_id)
        if self._list_open:
            self._render_list()

    def _show_cover(self, video_id):
        if video_id == self._shown_thumb:
            return
        img = self.app.covers.get(video_id, (64, 36))
        if img:
            self.cover.configure(image=img, text="")
            self._shown_thumb = video_id

    @staticmethod
    def _short(text, n):
        return text if len(text) <= n else text[: n - 1] + "…"

    def _restore(self):
        self.app.undock()
