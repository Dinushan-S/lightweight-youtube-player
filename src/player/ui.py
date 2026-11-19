import io
import os
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox
import urllib.request
from typing import Optional, List

import customtkinter as ctk
import darkdetect
from PIL import Image

from src.player.controller import PlayerController, is_playlist_url
from src.player.desktop import dispatch_media_key, listen_media_keys, start_tray
from src.player.models import PlaybackState, RepeatMode, Track

# assets/ sits next to src/ in the repo and at the bundle root in the .exe build
APP_ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        "assets", "icon.ico")


def format_time(seconds: float) -> str:
    total_sec = int(max(0, seconds))
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    secs = total_sec % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class Icon:
    """Segoe Fluent Icons / MDL2 Assets code points (same in both fonts, shipped with Windows)."""
    ADD = ""
    PIN = ""
    UNPIN = ""
    PLAY = ""
    PAUSE = ""
    PREV = ""
    NEXT = ""
    SHUFFLE = ""
    REPEAT_ALL = ""
    REPEAT_ONE = ""
    VOLUME_0 = ""
    VOLUME_1 = ""
    VOLUME_3 = ""
    MUTE = ""
    HEART = ""
    HEART_FILL = ""
    REMOVE = ""
    DOCK = ""
    RESTORE = ""
    MUSIC = ""
    CHEVRON_DOWN = ""
    CHEVRON_UP = ""
    THEME = ""


# Three minimalist looks over one layout. Each value is a design token; nothing else in the UI hard-codes colour.
THEMES = {
    # Dark and flat: no cards, no borders; hierarchy from type and one white accent.
    "graphite": dict(
        mode="Dark", bg="#111111", surface="#111111", raised="#1A1A1A", hover="#242424", border="#111111",
        border_width=0, text="#EDEDED", muted="#9A9A9A", accent="#F2F2F2", accent_hover="#FFFFFF",
        on_accent="#111111", active_row="#1F1F1F", track="#2A2A2A", radius=8, gap=24,
    ),
    # Light paper-white panels with hairline borders and a single cobalt accent.
    "porcelain": dict(
        mode="Light", bg="#F1F2F4", surface="#FFFFFF", raised="#F6F7F9", hover="#ECEEF2", border="#E1E4E8",
        border_width=1, text="#14161A", muted="#5E6570", accent="#2547F5", accent_hover="#1A35C4",
        on_accent="#FFFFFF", active_row="#EAEFFF", track="#E1E4E8", radius=14, gap=14,
    ),
    # One colour carries the whole window (deep indigo), with a warm apricot accent and round shapes.
    "indigo": dict(
        mode="Dark", bg="#161936", surface="#1E2246", raised="#252A55", hover="#2E3462", border="#1E2246",
        border_width=0, text="#F3F4FF", muted="#A9AEDA", accent="#FFB36B", accent_hover="#FFC68F",
        on_accent="#1A1B2E", active_row="#2B3060", track="#323868", radius=22, gap=16,
    ),
}
AUTO = "auto"  # follow Windows: Graphite in dark mode, Porcelain in light mode
DEFAULT_THEME = AUTO


def resolve_theme(choice: str) -> str:
    if choice in THEMES:
        return choice
    return "graphite" if darkdetect.isDark() else "porcelain"


class CoverCache:
    """YouTube thumbnails by video id. Fetched off-thread; images are made on the Tk thread when asked for."""

    def __init__(self):
        self._data = {}  # video_id -> "loading" | bytes (b"" = none) | PIL.Image
        self._images = {}  # (video_id, size) -> CTkImage

    def get(self, video_id: str, size) -> Optional[ctk.CTkImage]:
        v = self._data.get(video_id)
        if v is None:
            self._data[video_id] = "loading"
            threading.Thread(target=self._fetch, args=(video_id,), daemon=True).start()
            return None
        try:
            if isinstance(v, bytes):
                if not v:
                    return None
                img = Image.open(io.BytesIO(v))
                img.load()  # decode now, so a bad download fails here and not inside Tk later
                self._data[video_id] = v = img
            if isinstance(v, Image.Image):
                key = (video_id, size)
                if key not in self._images:
                    self._images[key] = ctk.CTkImage(v, size=size)
                return self._images[key]
        except Exception as e:  # not an image (captive portal, truncated body): no cover for this song
            print(f"[CoverCache] Bad thumbnail for {video_id}: {e}")
            self._data[video_id] = b""
        return None

    def _fetch(self, video_id: str):
        try:
            with urllib.request.urlopen(f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg", timeout=10) as r:
                self._data[video_id] = r.read()
        except Exception:  # OSError, IncompleteRead, ...: never leave the entry stuck on "loading"
            self._data[video_id] = b""


def show_cover(label: ctk.CTkLabel, image: Optional[ctk.CTkImage], placeholder: str):
    """Put `image` on a cover label, or the placeholder glyph when there is none."""
    if image:
        label.configure(image=image, text="")
    else:
        label.configure(image=None, text=placeholder)
        label._label.configure(image="")  # CTk leaves the old picture on its inner label when given None


class MusicPlayerApp(ctk.CTk):
    """Minimal, lightweight YouTube music player."""

    QUEUE_WINDOW = 60
    COVER = (176, 99)  # 16:9, logical px

    def __init__(self, controller: Optional[PlayerController] = None, theme: Optional[str] = None):
        self.controller = controller or PlayerController()
        saved = self.controller.get_setting("theme", DEFAULT_THEME)
        self.theme_choice = theme or (saved if saved in THEMES else AUTO)
        theme = resolve_theme(self.theme_choice)
        ctk.set_appearance_mode(THEMES[theme]["mode"])
        super().__init__()

        families = set(tkfont.families(self))
        self.ICON_FONT = "Segoe Fluent Icons" if "Segoe Fluent Icons" in families else "Segoe MDL2 Assets"
        self.FONT = "Segoe UI Variable Text" if "Segoe UI Variable Text" in families else "Segoe UI"
        self.FONT_DISPLAY = "Segoe UI Variable Display" if "Segoe UI Variable Display" in families else "Segoe UI"

        self.covers = CoverCache()
        self._is_seeking = False
        self._status_error = False
        self._loading = False  # a pasted link is being looked up
        self._open_token = 0  # bumped per open / Cancel; a finished lookup with an old token is ignored
        self._cached_history: List[Track] = []
        self.mini = None

        self.title("Lightweight YouTube Player")
        if os.path.exists(APP_ICON):
            self.iconbitmap(APP_ICON)
        self.geometry("880x560")
        self.minsize(700, 460)

        self.controller.add_state_listener(self._on_player_state_change)
        self.controller.add_timeline_listener(self._on_timeline_update)
        self.controller.add_history_listener(self._refresh_history_ui)
        self.controller.add_queue_listener(self._on_queue_change)
        self.controller.add_favorites_listener(lambda: self.after(0, self._refresh_favorites))
        self.controller.add_playlists_listener(lambda: self.after(0, self._refresh_playlists))

        self._load_theme(theme)
        self._cover_tick()
        self._follow_windows_mode()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        for key in ("<Control-m>", "<Control-M>"):
            self.bind(key, lambda e: self.toggle_view())

        # Background use: media keys anywhere, and a tray icon that closing/minimizing hides the window into
        listen_media_keys(lambda vk: dispatch_media_key(self.controller, vk))
        self.tray = start_tray(APP_ICON, self.controller, show=lambda: self.after(0, self.show_window),
                               quit_app=lambda: self.after(0, self.quit_app))
        self._tray_tip_shown = False
        self.bind("<Unmap>", self._on_unmap)

    def _load_theme(self, name: str):
        """(Re)build every widget in theme `name`, then repaint the current player state into it."""
        # Carry in-progress UI state across the rebuild (a link mid-load must keep Play disabled)
        old = None
        if hasattr(self, "tabs"):
            old = dict(tab=self.tabs.get(), url=self.url_entry.get(),
                       loading=self._loading,
                       status=self.status_label.cget("text"), status_error=self._status_error)
        self._is_seeking = False  # the slider being dragged is about to be destroyed
        self.theme_name, self.t = name, THEMES[name]
        # Changing light/dark makes CTk re-focus the previously focused widget a moment later;
        # that widget is about to be destroyed, so park focus on the window first.
        self.focus_set()
        ctk.set_appearance_mode(self.t["mode"])
        self.configure(fg_color=self.t["bg"])
        for child in self.winfo_children():
            if not isinstance(child, ctk.CTkToplevel):
                child.destroy()
        self._shown_cover = None
        self._build_widgets()
        if old:
            self._select_tab(old["tab"])
            self.url_entry.insert(0, old["url"])
            if old["loading"]:
                self._set_loading(True)
            self._set_status(old["status"], error=old["status_error"])

        c = self.controller
        self._refresh_history_ui()
        self._refresh_favorites()
        self._render_queue()
        self._refresh_playlists()
        if c.current_track:
            self._on_player_state_change(c.state, c.current_track)
            self._on_timeline_update(c.time_pos, c.duration)
        else:
            self._show_idle_text()

    def set_theme(self, choice: str):
        """`choice` is a theme name or AUTO; it is saved and used on the next launch."""
        self.theme_choice = choice
        self.controller.set_setting("theme", choice)
        name = resolve_theme(choice)
        if name != self.theme_name:
            self._load_theme(name)

    def _follow_windows_mode(self):
        """In AUTO, switch Graphite/Porcelain when Windows switches dark/light (checked every 2 s)."""
        if self.theme_choice == AUTO and self.mini is None and not self._is_seeking:
            name = resolve_theme(AUTO)
            if name != self.theme_name:
                self._load_theme(name)
        self.after(2000, self._follow_windows_mode)

    def _show_theme_menu(self):
        menu = tk.Menu(self, tearoff=0)
        choice = tk.StringVar(master=menu, value=self.theme_choice)
        menu.add_radiobutton(label="Match Windows (Graphite / Porcelain)", variable=choice, value=AUTO,
                             command=lambda: self.after(10, self.set_theme, AUTO))
        menu.add_separator()
        for name in THEMES:
            menu.add_radiobutton(label=name.title(), variable=choice, value=name,
                                 command=lambda n=name: self.after(10, self.set_theme, n))
        b = self.theme_btn
        menu.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())

    # --- building blocks -------------------------------------------------------------
    def _panel(self, parent, **kw):
        t = self.t
        return ctk.CTkFrame(parent, fg_color=t["surface"], corner_radius=t["radius"],
                            border_width=t["border_width"], border_color=t["border"], **kw)

    def _icon_btn(self, parent, glyph, command, size=36, font_size=14, muted=False, pack=True):
        t = self.t
        btn = ctk.CTkButton(
            parent, text=glyph, width=size, height=size, corner_radius=size // 2,
            fg_color="transparent", hover_color=t["hover"],
            text_color=t["muted"] if muted else t["text"],
            font=(self.ICON_FONT, font_size), command=command,
        )
        if pack:
            btn.pack(side="left", padx=3)
        return btn

    def _label(self, parent, text="", size=12, bold=False, muted=False, display=False, **kw):
        t = self.t
        return ctk.CTkLabel(
            parent, text=text, text_color=t["muted"] if muted else t["text"],
            font=(self.FONT_DISPLAY if display else self.FONT, size, "bold" if bold else "normal"), **kw,
        )

    def _slider(self, parent, **kw):
        t = self.t
        return ctk.CTkSlider(parent, fg_color=t["track"], progress_color=t["accent"], button_color=t["accent"],
                             button_hover_color=t["accent_hover"], **kw)

    def _scroll(self, parent):
        t = self.t
        return ctk.CTkScrollableFrame(parent, fg_color="transparent", scrollbar_button_color=t["track"],
                                      scrollbar_button_hover_color=t["hover"])

    def _build_widgets(self):
        t = self.t
        gap = t["gap"]

        # Link bar
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=gap, pady=(gap, gap // 2))
        self.url_entry = ctk.CTkEntry(
            top, placeholder_text="Paste a YouTube song or playlist link", height=40,
            corner_radius=min(t["radius"], 20), fg_color=t["surface"] if t["border_width"] else t["raised"],
            border_width=t["border_width"], border_color=t["border"], text_color=t["text"],
            placeholder_text_color=t["muted"], font=(self.FONT, 13),
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.url_entry.bind("<Return>", lambda e: self._open_from_box())  # a new link replaces one still loading
        self.play_url_btn = ctk.CTkButton(
            top, text="Play", width=84, height=40, corner_radius=min(t["radius"], 20),
            fg_color=t["accent"], hover_color=t["accent_hover"], text_color=t["on_accent"],
            text_color_disabled=t["on_accent"], font=(self.FONT, 13, "bold"), command=self._on_play_click,
        )
        self.play_url_btn.pack(side="left")
        self.dock_btn = self._icon_btn(top, Icon.DOCK, self.dock, size=40, font_size=15, muted=True, pack=False)
        self.dock_btn.pack(side="left", padx=(6, 0))
        self.theme_btn = self._icon_btn(top, Icon.THEME, self._show_theme_menu, size=40, font_size=15,
                                        muted=True, pack=False)
        self.theme_btn.pack(side="left")

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=gap, pady=(gap // 2, gap))

        # Right: History / Tracklist / Favorites
        side = self._panel(content, width=320)
        side.pack(side="right", fill="both")
        side.pack_propagate(False)
        self.tabs = ctk.CTkTabview(
            side, fg_color="transparent", segmented_button_fg_color=t["raised"],
            segmented_button_selected_color=t["accent"], segmented_button_selected_hover_color=t["accent_hover"],
            segmented_button_unselected_color=t["raised"], segmented_button_unselected_hover_color=t["hover"],
            text_color=t["text"], corner_radius=min(t["radius"], 16),
        )
        self.tabs._segmented_button.configure(font=(self.FONT, 12), text_color=t["text"])
        self.tabs.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        history_tab = self.tabs.add("History")
        queue_tab = self.tabs.add("Tracklist")
        fav_tab = self.tabs.add("Favorites")
        pl_tab = self.tabs.add("Playlists")
        # Selected tab text sits on the accent colour
        self.tabs._segmented_button.configure(command=lambda v: (self._tint_tabs(), self.tabs._segmented_button_callback(v)))
        self._tint_tabs()

        self.hist_search = ctk.CTkEntry(
            history_tab, placeholder_text="Search history", height=32, corner_radius=min(t["radius"], 16),
            fg_color=t["raised"], border_width=0, text_color=t["text"],
            placeholder_text_color=t["muted"], font=(self.FONT, 12),
        )
        self.hist_search.pack(fill="x", padx=4, pady=(2, 6))
        self.hist_search.bind("<KeyRelease>", lambda e: self._filter_history_ui())
        self.history_scroll = self._scroll(history_tab)
        self.history_scroll.pack(fill="both", expand=True)
        self.queue_scroll = self._scroll(queue_tab)
        self.queue_scroll.pack(fill="both", expand=True)
        self.fav_scroll = self._scroll(fav_tab)
        self.fav_scroll.pack(fill="both", expand=True)
        ctk.CTkButton(
            pl_tab, text="+  New playlist", height=32, corner_radius=min(t["radius"], 16), fg_color=t["raised"],
            hover_color=t["hover"], text_color=t["text"], font=(self.FONT, 12), command=self._new_playlist,
        ).pack(fill="x", padx=4, pady=(2, 6))
        self.pl_scroll = self._scroll(pl_tab)
        self.pl_scroll.pack(fill="both", expand=True)

        # Left: now playing
        now = self._panel(content)
        now.pack(side="left", fill="both", expand=True, padx=(0, gap))
        inner = ctk.CTkFrame(now, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=gap, pady=gap)

        head = ctk.CTkFrame(inner, fg_color="transparent")
        head.pack(fill="x")
        self.cover_label = ctk.CTkLabel(
            head, text=Icon.MUSIC, width=self.COVER[0], height=self.COVER[1], corner_radius=min(t["radius"], 10),
            fg_color=t["raised"], text_color=t["muted"], font=(self.ICON_FONT, 28),
        )
        self.cover_label.pack(side="left", anchor="n")
        meta = ctk.CTkFrame(head, fg_color="transparent")
        meta.pack(side="left", fill="both", expand=True, padx=(16, 0))
        self.title_label = self._label(meta, size=17, bold=True, display=True, anchor="w", justify="left")
        self.title_label.pack(fill="x", anchor="w")
        self.channel_label = self._label(meta, size=12, muted=True, anchor="w", justify="left")
        self.channel_label.pack(fill="x", anchor="w", pady=(4, 0))
        self.status_label = self._label(meta, size=11, muted=True, anchor="w", justify="left")  # packed only when it has text
        self.song_actions = ctk.CTkFrame(meta, fg_color="transparent")
        self.song_actions.pack(anchor="w", pady=(6, 0))
        self.fav_btn = self._icon_btn(self.song_actions, Icon.HEART, self.toggle_favorite, size=34, font_size=15,
                                      muted=True, pack=False)
        self.fav_btn.pack(side="left")
        self.add_btn = self._icon_btn(self.song_actions, Icon.ADD, self._show_add_menu, size=34, font_size=14,
                                      muted=True, pack=False)
        self.add_btn.pack(side="left", padx=(4, 0))
        # Wrap text to the space the window actually gives it (CTk scales wraplength itself)
        meta.bind("<Configure>", lambda e: [
            w.configure(wraplength=max(120, e.width / self._get_window_scaling() - 8))
            for w in (self.title_label, self.channel_label, self.status_label)
        ])

        # Seek
        timeline = ctk.CTkFrame(inner, fg_color="transparent")
        timeline.pack(fill="x", pady=(gap, 4))
        self.seek_slider = self._slider(timeline, from_=0, to=100, height=14, command=self._on_seek_drag)
        self.seek_slider.set(0)
        self.seek_slider.pack(fill="x")
        self.seek_slider.bind("<ButtonRelease-1>", self._on_seek_release)
        times = ctk.CTkFrame(timeline, fg_color="transparent")
        times.pack(fill="x", padx=4)
        self.time_elapsed_label = self._label(times, "00:00", size=11, muted=True)
        self.time_elapsed_label.pack(side="left")
        self.time_total_label = self._label(times, "00:00", size=11, muted=True)
        self.time_total_label.pack(side="right")

        # Transport
        transport = ctk.CTkFrame(inner, fg_color="transparent")
        transport.pack(pady=(4, 0))
        self.shuffle_btn = self._icon_btn(transport, Icon.SHUFFLE, self._on_shuffle_click, muted=True)
        self.prev_btn = self._icon_btn(transport, Icon.PREV, self._on_prev_click, font_size=16)
        self.toggle_btn = self._icon_btn(transport, Icon.PLAY, self._on_toggle_play_pause, size=54, font_size=20)
        self.toggle_btn.configure(fg_color=t["accent"], hover_color=t["accent_hover"], text_color=t["on_accent"])
        self.toggle_btn.pack_configure(padx=10)
        self.next_btn = self._icon_btn(transport, Icon.NEXT, self._on_next_click, font_size=16)
        self.repeat_btn = self._icon_btn(transport, Icon.REPEAT_ALL, self._on_repeat_click, muted=True)

        # Volume
        bottom = ctk.CTkFrame(inner, fg_color="transparent")
        bottom.pack(fill="x", side="bottom")
        self.vol_pct_label = self._label(bottom, size=11, muted=True, width=40, anchor="e")
        self.vol_pct_label.pack(side="right")
        self.volume_slider = self._slider(bottom, from_=0, to=100, number_of_steps=100, width=120, height=14,
                                          command=self._on_volume_change)
        self.volume_slider.set(self.controller.volume)
        self.volume_slider.pack(side="right", padx=(4, 6))
        self.volume_slider.bind("<MouseWheel>", self.on_volume_wheel)
        self.mute_btn = self._icon_btn(bottom, Icon.VOLUME_3, self._on_mute_click, size=32, font_size=13,
                                       pack=False)
        self.mute_btn.pack(side="right")
        self._refresh_volume_ui()

    def _tint_tabs(self):
        seg = self.tabs._segmented_button
        current = seg.get()
        for name, button in seg._buttons_dict.items():
            button.configure(text_color=self.t["on_accent"] if name == current else self.t["text"])

    # --- actions ---------------------------------------------------------------
    def _on_play_click(self):
        """The Play button: Cancel while a link is loading."""
        if self._loading:
            self._cancel_open()
        else:
            self._open_from_box()

    def _open_from_box(self):
        """Open the pasted link (replacing one still loading), or with an empty box resume the last song."""
        url = self.url_entry.get().strip()
        if not url:
            last = self.controller.get_history(limit=1)
            if last:
                self._play_from_history(last[0])
            return

        self._open_token += 1
        token = self._open_token
        self._set_loading(True)
        self._set_status("Finding the audio stream…")
        if is_playlist_url(url):
            self._select_tab("Tracklist")

        def on_done(ok: bool):
            def update_ui():
                if token != self._open_token:
                    return  # cancelled, or replaced by a newer link
                self._set_loading(False)
                self._set_status("" if ok else "Couldn't play that link. Check it and try again.", error=not ok)
            self.after(0, update_ui)

        self.controller.open_url_async(url, on_complete=on_done)

    def _cancel_open(self):
        self._open_token += 1
        self.controller.cancel_open()
        self._set_loading(False)
        self._set_status("")
        self.url_entry.focus_set()
        self.url_entry.select_range(0, "end")  # ready to paste over the wrong link

    def _set_loading(self, on: bool):
        self._loading = on
        t = self.t
        self.play_url_btn.configure(
            text="Cancel" if on else "Play",
            fg_color=t["raised"] if on else t["accent"], hover_color=t["hover"] if on else t["accent_hover"],
            text_color=t["text"] if on else t["on_accent"],
        )

    def _set_status(self, text: str, error: bool = False):
        self._status_error = error
        self.status_label.configure(text=text, text_color=self.t["accent"] if error else self.t["muted"])
        if text:
            self.status_label.pack(fill="x", anchor="w", pady=(2, 0), before=self.song_actions)
        else:
            self.status_label.pack_forget()

    def _select_tab(self, name):
        self.tabs.set(name)
        self._tint_tabs()

    def _on_toggle_play_pause(self):
        if self.controller.current_track is None:
            if not self._loading:
                self._open_from_box()  # nothing loaded yet: pasted link, else last history song
        else:
            self.controller.toggle_play_pause()

    def _on_prev_click(self):
        self.controller.prev_track()

    def _on_next_click(self):
        self.controller.next_track()

    def _on_shuffle_click(self):
        self.controller.toggle_shuffle()

    def _on_repeat_click(self):
        cycle = [RepeatMode.OFF, RepeatMode.ALL, RepeatMode.ONE]
        self.controller.set_repeat_mode(cycle[(cycle.index(self.controller.repeat_mode) + 1) % len(cycle)])

    def toggle_favorite(self, track: Optional[Track] = None):
        track = track or self.controller.current_track
        if track:
            self.controller.set_favorite(track, not self.controller.is_favorite(track.video_id))

    # --- lists -------------------------------------------------------------------
    def _row(self, parent, title, meta, on_click, active=False, action=None, menu=None):
        """One list row: title over meta, optional trailing icon action, optional right-click menu (a builder)."""
        t = self.t
        row = ctk.CTkFrame(parent, fg_color=t["active_row"] if active else "transparent",
                           corner_radius=min(t["radius"], 10), cursor="hand2")
        row.pack(fill="x", pady=1)
        if action:
            glyph, cmd, color = action
            btn = self._icon_btn(row, glyph, cmd, size=28, font_size=11, pack=False)
            btn.configure(text_color=color)
            btn.pack(side="right", padx=(0, 6))
        text = ctk.CTkFrame(row, fg_color="transparent")
        text.pack(side="left", fill="x", expand=True, padx=10, pady=6)
        title_lbl = self._label(text, title, size=12, bold=active, anchor="w")
        if active:
            title_lbl.configure(text_color=t["accent"])
        title_lbl.pack(fill="x")
        meta_lbl = self._label(text, meta, size=10, muted=True, anchor="w")
        meta_lbl.pack(fill="x")
        for w in (row, text, title_lbl, meta_lbl):
            w.bind("<Button-1>", lambda e: on_click())
            if menu:
                w.bind("<Button-3>", lambda e: menu().tk_popup(e.x_root, e.y_root))
        return row

    # --- own playlists -------------------------------------------------------------
    def _flash(self, text: str, error: bool = False):
        """Short-lived status line (e.g. "Added to Deep Work")."""
        self._set_status(text, error=error)
        self.after(3000, lambda: self.status_label.winfo_exists() and self.status_label.cget("text") == text
                   and self._set_status(""))

    def _ask_name(self, title: str) -> Optional[str]:
        t = self.t
        name = ctk.CTkInputDialog(
            title=title, text="Name", fg_color=t["bg"], text_color=t["text"], button_fg_color=t["accent"],
            button_hover_color=t["accent_hover"], button_text_color=t["on_accent"], entry_fg_color=t["raised"],
            entry_border_color=t["border"], entry_text_color=t["text"], font=(self.FONT, 12),
        ).get_input()
        return name.strip() if name and name.strip() else None

    def _new_playlist(self, then=None):
        """Ask for a name, create the playlist, then call then(playlist_id, title)."""
        name = self._ask_name("New playlist")
        if name:
            pid = self.controller.create_playlist(name)
            if then:
                then(pid, name)

    def _add_choices(self, menu, add):
        """Fill `menu` with the user's own playlists (+ New playlist…); picking one calls add(playlist_id, title)."""
        for p in self.controller.get_playlists():
            if p["source_type"] == "local":  # imported ones are replaced on re-import, so additions would vanish
                menu.add_command(label=self._short(p["title"], 40),
                                 command=lambda p=p: add(p["id"], p["title"]))
        if menu.index("end") is not None:
            menu.add_separator()
        # after(): let the menu close before the dialog grabs input
        menu.add_command(label="New playlist…", command=lambda: self.after(10, self._new_playlist, add))
        return menu

    def _add_track_to(self, track: Track):
        def add(pid, title):
            self.controller.add_to_playlist(pid, track)
            self._flash(f"Added to {title}")
        return add

    def _add_submenu(self, menu, track: Track):
        menu.add_cascade(label="Add to playlist",
                         menu=self._add_choices(tk.Menu(menu, tearoff=0), self._add_track_to(track)))

    def _song_menu(self, track: Track):
        menu = tk.Menu(self, tearoff=0)
        self._add_submenu(menu, track)
        return menu

    def _show_add_menu(self):
        """The + under the title: adds the pasted song link if there is a new one, otherwise the playing song."""
        url = self.url_entry.get().strip()
        current = self.controller.current_track
        menu = tk.Menu(self, tearoff=0)
        if url and not is_playlist_url(url) and not (current and current.video_id in url):
            def add(pid, title):
                self._flash(f"Adding the link to {title}…")
                self.controller.add_url_to_playlist_async(pid, url, on_complete=lambda ok: self.after(
                    0, self._flash, f"Added to {title}" if ok else "Couldn't add that link", not ok))
            menu.add_command(label="Add the pasted link to:", state="disabled")
        elif current:
            add = self._add_track_to(current)
            menu.add_command(label=f"Add “{self._short(current.title, 30)}” to:", state="disabled")
        else:
            self._flash("Play a song or paste a link first")
            return
        menu.add_separator()
        self._add_choices(menu, add)
        b = self.add_btn
        menu.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())

    def _queue_menu(self, i: int, track: Track):
        n = len(self.controller.queue_tracks)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Move up", state="normal" if i > 0 else "disabled",
                         command=lambda: self.controller.move_in_queue(i, i - 1))
        menu.add_command(label="Move down", state="normal" if i < n - 1 else "disabled",
                         command=lambda: self.controller.move_in_queue(i, i + 1))
        menu.add_separator()
        self._add_submenu(menu, track)
        menu.add_command(label="Remove", command=lambda: self.controller.remove_from_queue(i))
        return menu

    def _refresh_playlists(self):
        for w in self.pl_scroll.winfo_children():
            w.destroy()
        playlists = self.controller.get_playlists()
        if not playlists:
            self._empty(self.pl_scroll, "Make a playlist, then right-click any song (or use + under the title) to add it")
        for p in playlists:
            n = p["track_count"]
            meta = f"{n} song{'' if n == 1 else 's'}" + ("" if p["source_type"] == "local" else " · from YouTube")
            self._row(
                self.pl_scroll, self._short(p["title"]), meta, lambda p=p: self._open_playlist(p),
                active=p["id"] == self.controller.playlist_id,
                action=(Icon.REMOVE, lambda p=p: self._delete_playlist(p), self.t["muted"]),
                menu=lambda p=p: self._playlist_menu(p),
            )

    def _playlist_menu(self, p):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Play", command=lambda: self._open_playlist(p))
        menu.add_command(label="Rename…", command=lambda: self.after(10, self._rename_playlist, p))
        menu.add_command(label="Delete…", command=lambda: self.after(10, self._delete_playlist, p))
        return menu

    def _open_playlist(self, p):
        if self.controller.play_playlist(p["id"]):
            self._select_tab("Tracklist")
        else:
            self._flash("This playlist is empty. Right-click a song to add it.")

    def _rename_playlist(self, p):
        name = self._ask_name(f"Rename “{self._short(p['title'], 30)}”")
        if name:
            self.controller.rename_playlist(p["id"], name)

    def _delete_playlist(self, p):
        if messagebox.askyesno("Delete playlist", f"Delete “{p['title']}”?\n\nThe songs stay in History and Favorites.",
                               parent=self):
            self.controller.delete_playlist(p["id"])

    def _empty(self, parent, text):
        self._label(parent, text, size=11, muted=True, wraplength=240).pack(pady=24)

    @staticmethod
    def _short(text, n=38):
        return text if len(text) <= n else text[: n - 1] + "…"

    def _on_queue_change(self):
        self.after(0, self._render_queue)
        self.after(0, self._refresh_playlists)  # song counts and the highlighted (open) playlist

    def _render_queue(self):
        for widget in self.queue_scroll.winfo_children():
            widget.destroy()

        tracks = self.controller.queue_tracks
        if not tracks:
            self._empty(self.queue_scroll, "Paste a playlist link to see its songs here")

        active = self.controller.queue_index
        current = self.controller.current_track
        # Big playlists (1000+ songs) freeze Tk if every row is a widget: render a window around the active track.
        first = max(0, active - 5)
        shown = tracks[first:first + self.QUEUE_WINDOW]
        for i, track in enumerate(shown, start=first):
            self._row(
                self.queue_scroll, f"{i + 1}. {self._short(track.title)}",
                f"{track.channel} · {format_time(track.duration_sec)}",
                lambda i=i: self.controller.play_queue_index(i),
                active=bool(current and track.video_id == current.video_id),
                action=(Icon.REMOVE, lambda i=i: self.controller.remove_from_queue(i), self.t["muted"]),
                menu=lambda i=i, tr=track: self._queue_menu(i, tr),
            )

        if len(tracks) > len(shown):
            self._label(self.queue_scroll, f"Showing {first + 1}–{first + len(shown)} of {len(tracks)}",
                        size=10, muted=True).pack(pady=8)

        t = self.t
        self.shuffle_btn.configure(text_color=t["accent"] if self.controller.is_shuffle else t["muted"])
        repeat = self.controller.repeat_mode
        self.repeat_btn.configure(
            text=Icon.REPEAT_ONE if repeat == RepeatMode.ONE else Icon.REPEAT_ALL,
            text_color=t["muted"] if repeat == RepeatMode.OFF else t["accent"],
        )

    def _refresh_favorites(self):
        for w in self.fav_scroll.winfo_children():
            w.destroy()
        favs = self.controller.get_favorites()
        if not favs:
            self._empty(self.fav_scroll, "Tap the heart on a song to keep it here")
        for track in favs:
            self._row(
                self.fav_scroll, self._short(track.title), f"{track.channel} · {format_time(track.duration_sec)}",
                lambda tr=track: self._play_from_history(tr),
                action=(Icon.HEART_FILL, lambda tr=track: self.controller.set_favorite(tr, False), self.t["accent"]),
                menu=lambda tr=track: self._song_menu(tr),
            )
        self._refresh_fav_btn()

    def _refresh_fav_btn(self):
        track = self.controller.current_track
        on = bool(track and self.controller.is_favorite(track.video_id))
        self.fav_btn.configure(text=Icon.HEART_FILL if on else Icon.HEART,
                               text_color=self.t["accent"] if on else self.t["muted"],
                               state="normal" if track else "disabled")

    # --- volume ---------------------------------------------------------------------
    def _on_volume_change(self, val):
        self.controller.set_volume(int(val))
        self.volume_slider.set(self.controller.volume)  # mouse-wheel path doesn't move the slider itself
        self._refresh_volume_ui()

    def on_volume_wheel(self, event):
        # 5% per notch; Windows may merge several notches into one event (delta = ±120 each).
        self._on_volume_change(self.controller.volume + round(5 * event.delta / 120))

    def _on_mute_click(self):
        self.controller.toggle_mute()
        self._refresh_volume_ui()

    def _refresh_volume_ui(self):
        self.mute_btn.configure(text=self.volume_icon(),
                                text_color=self.t["accent"] if self.controller.muted else self.t["text"])
        self.vol_pct_label.configure(text=self.volume_text())

    def volume_icon(self) -> str:
        vol, muted = self.controller.volume, self.controller.muted
        if muted:
            return Icon.MUTE
        return Icon.VOLUME_0 if vol == 0 else (Icon.VOLUME_1 if vol < 50 else Icon.VOLUME_3)

    def volume_text(self) -> str:
        return "Muted" if self.controller.muted else f"{self.controller.volume}%"

    # --- playback updates ---------------------------------------------------------------
    def _on_seek_drag(self, val):
        self._is_seeking = True
        self.time_elapsed_label.configure(text=format_time(val))

    def _on_seek_release(self, event):
        self.controller.seek(float(self.seek_slider.get()))
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
            self.toggle_btn.configure(text=Icon.PAUSE if state == PlaybackState.PLAYING else Icon.PLAY)
            if track:
                self.title_label.configure(text=self._short(track.title, 52))  # two lines at most
                self.channel_label.configure(text=f"{track.channel} · {track.format_badge}")
                if track.duration_sec > 0:
                    self.time_total_label.configure(text=format_time(track.duration_sec))
                    self.seek_slider.configure(to=track.duration_sec)
            self._refresh_fav_btn()

        self.after(0, update)

    def _show_idle_text(self):
        self.title_label.configure(text="Paste a link to start listening")
        has_history = bool(self._cached_history or self.controller.get_history(limit=1))
        self.channel_label.configure(
            text="Or press play to pick up your last song" if has_history else "Songs and playlists from YouTube, audio only"
        )
        self._refresh_fav_btn()

    def _cover_tick(self):
        try:
            track = self.controller.current_track
            vid = track.video_id if track else None
            if vid and self._shown_cover != (vid, True):
                img = self.covers.get(vid, self.COVER)
                # New song without a cover yet (or none at all): placeholder, never the previous song's art
                if (vid, bool(img)) != self._shown_cover:
                    show_cover(self.cover_label, img, Icon.MUSIC)
                    self._shown_cover = (vid, bool(img))
        finally:
            self.after(300, self._cover_tick)  # keep ticking even if a draw fails once

    # --- history -----------------------------------------------------------------------
    def _refresh_history_ui(self):
        def update():
            self._cached_history = self.controller.get_history()
            self._filter_history_ui()
        self.after(0, update)

    def _filter_history_ui(self):
        query = self.hist_search.get().strip().lower()
        tracks = [t for t in self._cached_history
                  if not query or query in t.title.lower() or query in t.channel.lower()]
        for widget in self.history_scroll.winfo_children():
            widget.destroy()
        if not tracks:
            self._empty(self.history_scroll, "No songs match" if query else "Songs you play show up here")
            return
        for track in tracks:
            self._row(self.history_scroll, self._short(track.title),
                      f"{track.channel} · {format_time(track.duration_sec)}",
                      lambda tr=track: self._play_from_history(tr), menu=lambda tr=track: self._song_menu(tr))

    def _play_from_history(self, track: Track):
        # The saved stream URL expires within hours; the watch link always re-resolves.
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, f"https://www.youtube.com/watch?v={track.video_id}")
        self._open_from_box()  # replaces a link still loading

    # --- dock -----------------------------------------------------------------------------
    def dock(self):
        """Hide the main window and pin the mini player to the top of the screen."""
        from src.player.mini_player import MiniPlayer  # lazy: mini_player imports this module
        if self.mini:
            return
        self.withdraw()
        self.mini = MiniPlayer(self)
        self.controller.set_view("mini")

    def undock(self):
        if self.mini:
            self.mini.destroy()
            self.mini = None
        self.controller.set_view("full")
        self.deiconify()
        self.lift()

    def toggle_view(self):
        """Ctrl+M: full window <-> docked mini player."""
        self.dock() if self.controller.view == "full" else self.undock()

    # --- tray / window close -------------------------------------------------------------
    def show_window(self):
        self.undock()  # also brings the main window back from the tray
        self.focus_force()

    def _on_unmap(self, event):
        # Minimize (not the dock's withdraw) sends the window to the tray
        if event.widget is self and self.tray and self.state() == "iconic":
            self.withdraw()

    def _on_close(self):
        if not self.tray:
            self.quit_app()
            return
        self.withdraw()  # keep playing in the tray
        if not self._tray_tip_shown:
            self._tray_tip_shown = True
            self.tray.notify("Still playing here. Right-click the tray icon to quit.", "Lightweight YouTube Player")

    def quit_app(self):
        if self.tray:
            self.tray.stop()
        self.controller.stop()
        self.destroy()


if __name__ == "__main__":
    app = MusicPlayerApp()
    app.mainloop()
