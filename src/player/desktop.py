"""Windows integration: global media keys and the system tray icon."""
import ctypes
import ctypes.wintypes
import sys
import threading
from typing import Callable, Optional

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
MEDIA_ACTIONS = {
    VK_MEDIA_PLAY_PAUSE: "toggle_play_pause",
    VK_MEDIA_NEXT_TRACK: "next_track",
    VK_MEDIA_PREV_TRACK: "prev_track",
}
WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000


def dispatch_media_key(controller, vk: int) -> bool:
    """Run the PlayerController action for media key `vk`. False if the key isn't one we handle."""
    name = MEDIA_ACTIONS.get(vk)
    if name is None:
        return False
    getattr(controller, name)()
    return True


def listen_media_keys(on_key: Callable[[int], None]):
    """Call on_key(vk) for Play/Pause, Next and Previous pressed anywhere (keyboard or headset), on a background thread.

    Uses RegisterHotKey, so while the player runs it owns these keys system-wide.
    """
    if sys.platform != "win32":
        return

    def loop():
        user32 = ctypes.windll.user32
        for vk in MEDIA_ACTIONS:
            # Hotkeys registered without a window post WM_HOTKEY to this thread; the id is the key code.
            if not user32.RegisterHotKey(None, vk, MOD_NOREPEAT, vk):
                print(f"[MediaKeys] Key 0x{vk:X} is taken by another app; it won't control the player")
        msg = ctypes.wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                try:
                    on_key(msg.wParam)
                except Exception as e:  # one failed action must not end the listener
                    print(f"[MediaKeys] {e}")

    threading.Thread(target=loop, daemon=True, name="media-keys").start()


def start_tray(icon_path: str, controller, show: Callable[[], None], quit_app: Callable[[], None]):
    """Tray icon with Show / Play-Pause / Next / Previous / Quit. Returns the icon, or None if it can't start.

    Menu callbacks run on the tray thread: `show` and `quit_app` must hand off to the Tk thread themselves.
    """
    try:
        import pystray
        from PIL import Image
        from src.player.models import PlaybackState

        try:
            image = Image.open(icon_path)
        except OSError:
            image = Image.new("RGB", (64, 64), "#2547F5")
        playing = lambda item: controller.state == PlaybackState.PLAYING  # noqa: E731
        menu = pystray.Menu(
            pystray.MenuItem("Show player", lambda: show(), default=True),  # also the left-click action
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: "Pause" if playing(item) else "Play",
                             lambda: controller.toggle_play_pause()),
            pystray.MenuItem("Next", lambda: controller.next_track()),
            pystray.MenuItem("Previous", lambda: controller.prev_track()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: quit_app()),
        )
        icon = pystray.Icon("LightweightYouTubePlayer", image, "Lightweight YouTube Player", menu)

        def on_state(state, track):
            # Windows builds the tray menu ahead of time, so the Play/Pause label needs a rebuild.
            icon.title = ("♪ " + track.title)[:100] if track else "Lightweight YouTube Player"
            icon.update_menu()

        controller.add_state_listener(on_state)
        threading.Thread(target=icon.run, daemon=True, name="tray").start()
        return icon
    except Exception as e:
        print(f"[Tray] Not available: {e}")
        return None
