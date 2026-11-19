import os
import sys
import json
import time
import shutil
import threading
import subprocess
from typing import Optional, Callable, Dict, Any

try:
    import win32file
    import win32pipe
    import pywintypes
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

# One pipe per app process: a second copy of the app (or an mpv orphaned by a crash) must not answer our commands.
PIPE_NAME = f"mpv_music_player_{os.getpid()}"

def find_mpv_binary() -> Optional[str]:
    """Finds the portable or installed mpv binary."""
    # Check local bin/ folder first
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    local_bin = os.path.join(base_dir, "bin", "mpv.exe")
    if os.path.exists(local_bin):
        return local_bin

    # Check winget package location
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        winget_path = os.path.join(
            local_app_data,
            "Microsoft",
            "WinGet",
            "Packages",
            "mpv-player.mpv-CI.MSVC_Microsoft.Winget.Source_8wekyb3d8bbwe",
            "mpv.exe",
        )
        if os.path.exists(winget_path):
            return winget_path

    # Check system PATH
    which_mpv = shutil.which("mpv")
    if which_mpv:
        return which_mpv

    return None

class MpvEngine:
    """Manages the headless MPV process and IPC communication."""

    def __init__(self, mpv_path: Optional[str] = None, pipe_name: str = PIPE_NAME):
        self.mpv_path = mpv_path or find_mpv_binary()
        self.pipe_name = pipe_name
        self._process: Optional[subprocess.Popen] = None
        self._handle = None
        self._is_running = False
        self._lock = threading.Lock()
        self._event_callbacks = []
        self._listener_thread: Optional[threading.Thread] = None

    @staticmethod
    def build_command(*args: Any) -> str:
        return json.dumps({"command": list(args)}) + "\n"

    @staticmethod
    def build_property(prop_name: str, value: Any) -> str:
        return json.dumps({"command": ["set_property", prop_name, value]}) + "\n"

    def start(self) -> bool:
        """Starts the headless mpv process. Returns True if it launched one, False if it was already running."""
        if self._process and self._process.poll() is None:
            return False

        if not self.mpv_path or not os.path.exists(self.mpv_path):
            raise FileNotFoundError(f"MPV binary not found at: {self.mpv_path}")

        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW

        ipc_name = self.pipe_name.removeprefix("\\\\.\\pipe\\")  # accept a bare name or a full \\.\pipe\ path
        pipe_path = rf"\\.\pipe\{ipc_name}"

        cmd = [
            self.mpv_path,
            "--no-video",
            "--idle",
            f"--input-ipc-server={ipc_name}",
            "--gapless-audio=yes",
            "--audio-pitch-correction=yes",
            "--force-window=no",
            "--reset-on-next-file=pause",  # Next/Prev while paused must play the new track
        ]

        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        self._is_running = True

        # Connect to IPC pipe with retries
        connected = False
        for _ in range(40):
            time.sleep(0.05)
            if HAS_WIN32 and sys.platform == "win32":
                try:
                    self._handle = win32file.CreateFile(
                        pipe_path,
                        win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                        0,
                        None,
                        win32file.OPEN_EXISTING,
                        0,
                        None,
                    )
                    connected = True
                    break
                except pywintypes.error:
                    continue
            else:
                try:
                    self._handle = open(pipe_path, "r+b", buffering=0)
                    connected = True
                    break
                except Exception:
                    continue

        if not connected:
            self.stop()
            raise ConnectionError(f"Could not connect to MPV IPC pipe: {pipe_path}")

        # Start event listener thread
        self._listener_thread = threading.Thread(target=self._listen_events, daemon=True)
        self._listener_thread.start()
        return True

    def _listen_events(self):
        """Reads JSON responses/events from MPV IPC non-blockingly."""
        buffer = ""
        while self._is_running and self._handle:
            try:
                if HAS_WIN32 and sys.platform == "win32":
                    try:
                        _, avail, _ = win32pipe.PeekNamedPipe(self._handle, 0)
                    except Exception:
                        break
                    if avail == 0:
                        time.sleep(0.05)
                        continue
                    hr, raw_data = win32file.ReadFile(self._handle, avail)
                    if hr != 0 or not raw_data:
                        break
                    chunk = raw_data.decode("utf-8", errors="ignore")
                else:
                    line = self._handle.readline()
                    if not line:
                        break
                    chunk = line.decode("utf-8", errors="ignore")

                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            for cb in self._event_callbacks:
                                try:
                                    cb(data)
                                except Exception as e:
                                    print(f"[MPV Event Callback Error] {e}")
                        except Exception:
                            pass
            except Exception:
                break

    def add_event_listener(self, callback: Callable[[Dict[str, Any]], None]):
        self._event_callbacks.append(callback)

    def send_command(self, *args: Any):
        """Sends a JSON command to MPV over the IPC pipe."""
        if not self._handle:
            return
        payload = self.build_command(*args).encode("utf-8")
        with self._lock:
            try:
                if HAS_WIN32 and sys.platform == "win32":
                    win32file.WriteFile(self._handle, payload)
                else:
                    self._handle.write(payload)
                    self._handle.flush()
            except Exception as e:
                print(f"[MPV Send Error] {e}")

    def set_property(self, prop: str, value: Any):
        self.send_command("set_property", prop, value)

    def load_stream(self, stream_url: str):
        self.send_command("loadfile", stream_url, "replace")

    def pause(self):
        self.set_property("pause", True)

    def resume(self):
        self.set_property("pause", False)

    def seek(self, seconds: float):
        self.send_command("seek", seconds, "absolute")

    def set_volume(self, volume: int):
        self.set_property("volume", max(0, min(100, volume)))

    def stop(self):
        self._is_running = False
        try:
            self.send_command("quit")
        except Exception:
            pass

        if self._process:
            try:
                self._process.wait(timeout=0.5)
            except Exception:
                try:
                    self._process.terminate()
                except Exception:
                    pass
            self._process = None

        if self._handle:
            try:
                if HAS_WIN32 and sys.platform == "win32":
                    win32file.CloseHandle(self._handle)
                else:
                    self._handle.close()
            except Exception:
                pass
            self._handle = None
