import time
import urllib.error
import urllib.request
import yt_dlp
from typing import Optional, Dict, Any, List, Tuple
from src.player.models import Track

class StreamResolver:
    """Extracts direct audio streams from YouTube using yt-dlp."""

    FORMAT_SELECTOR = "bestaudio[ext=opus]/bestaudio[ext=m4a]/bestaudio"

    def __init__(self, cookies_file: Optional[str] = None):
        self._cookies_file = cookies_file

    def get_format_selector(self) -> str:
        return self.FORMAT_SELECTOR

    def _get_ydl_opts(self) -> Dict[str, Any]:
        opts: Dict[str, Any] = {
            "format": self.FORMAT_SELECTOR,
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": False,
            "noplaylist": True,
        }
        if self._cookies_file:
            opts["cookiefile"] = self._cookies_file
        return opts

    @staticmethod
    def _wait_until_playable(url: str, headers: Dict[str, str], timeout: float = 4.0) -> bool:
        """Fresh googlevideo URLs answer 403 for their first ~0-1s; poll until they serve bytes.

        Returns False only if the URL is still 403 at the deadline (caller re-extracts).
        """
        req = urllib.request.Request(url, headers={**headers, "Range": "bytes=0-0"})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                urllib.request.urlopen(req, timeout=5).close()
                return True
            except urllib.error.HTTPError as e:
                if e.code != 403:
                    return True  # not the warm-up 403; let mpv report whatever it is
            except OSError:
                return True
            time.sleep(0.3)
        return False

    def resolve_track(self, url: str) -> Optional[Track]:
        """Resolves metadata and the direct audio stream URL for a given YouTube URL."""
        ydl_opts = self._get_ydl_opts()
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                for _ in range(2):  # re-extract once if the fresh URL stays 403
                    info = ydl.extract_info(url, download=False)
                    if not info:
                        return None
                    stream_url = info.get("url")
                    if not stream_url or self._wait_until_playable(stream_url, info.get("http_headers") or {}):
                        break
                # Detect format badge
                audio_ext = info.get("audio_ext") or info.get("ext") or "audio"
                abr = info.get("abr") or 160
                format_badge = f"{audio_ext.upper()} {int(abr)}k" if abr else audio_ext.upper()

                return Track(
                    video_id=info.get("id", ""),
                    title=info.get("title", "Unknown Title"),
                    channel=info.get("uploader") or info.get("channel") or "Unknown Artist",
                    duration_sec=int(info.get("duration") or 0),
                    stream_url=stream_url,
                    format_badge=format_badge,
                    thumbnail_url=info.get("thumbnail"),
                )
        except Exception as e:
            print(f"[StreamResolver] Error extracting {url}: {e}")
            return None

    def resolve_playlist(self, url: str) -> Tuple[str, List[Track]]:
        """Extract flat metadata for all tracks in a YouTube playlist.
        
        Returns (playlist_title, list_of_tracks) with no stream URLs resolved yet.
        """
        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": "in_playlist",
            "noplaylist": False,
        }
        if self._cookies_file:
            opts["cookiefile"] = self._cookies_file

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return ("", [])

                playlist_title = info.get("title", "Untitled Playlist")
                entries = info.get("entries") or []
                tracks: List[Track] = []
                for entry in entries:
                    if entry is None or not entry.get("title"):
                        continue  # deleted/private videos come back with no title and can't play
                    tracks.append(Track(
                        video_id=entry.get("id", ""),
                        title=entry.get("title", "Unknown Title"),
                        channel=entry.get("uploader") or entry.get("channel") or "Unknown Artist",
                        duration_sec=int(entry.get("duration") or 0),
                    ))
                return (playlist_title, tracks)
        except Exception as e:
            print(f"[StreamResolver] Error extracting playlist {url}: {e}")
            return ("", [])
