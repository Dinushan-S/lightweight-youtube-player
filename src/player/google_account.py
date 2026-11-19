"""Google sign-in (device flow: type a code at google.com/device) and reading the user's own YouTube playlists.

Standard library only. The refresh token is kept in the settings table, encrypted with Windows DPAPI
(only this Windows user on this PC can decrypt it).
"""
import base64
import ctypes
import glob
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from ctypes import wintypes
from typing import Callable, List, Optional, Tuple

from src.player.models import Track

SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
API = "https://www.googleapis.com/youtube/v3/"
DEVICE_CODE = "https://oauth2.googleapis.com/device/code"
MUSIC = "10"  # YouTube's "Music" video category
REVOKE = "https://oauth2.googleapis.com/revoke"
TOKEN_KEY = "google_refresh_token"
# Repo root in a source run, the bundle root in the .exe build (same layout trick as APP_ICON)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class SignedOut(Exception):
    """Not connected, or Google no longer accepts the saved sign-in (revoked or expired)."""


def load_client(folder: str = ROOT) -> Optional[dict]:
    """The "TVs and Limited Input devices" OAuth client downloaded from Google Cloud (client_secret*.json)."""
    for path in sorted(glob.glob(os.path.join(folder, "client_secret*.json"))):
        try:
            with open(path, encoding="utf-8") as fh:
                client = json.load(fh).get("installed")
        except (OSError, ValueError):
            continue
        if client and client.get("client_id"):
            return client
    return None


# --- DPAPI -------------------------------------------------------------------------------
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data: bytes, protect: bool) -> bytes:
    crypt32 = ctypes.windll.crypt32
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    buf = ctypes.create_string_buffer(data, len(data))
    src = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = _Blob()
    if not fn(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(out)):  # 1 = UI_FORBIDDEN
        raise OSError("Windows could not encrypt/decrypt the Google sign-in")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def encrypt(text: str) -> str:
    return base64.b64encode(_dpapi(text.encode(), True)).decode()


def decrypt(stored: str) -> str:
    return _dpapi(base64.b64decode(stored), False).decode()


# --- HTTP --------------------------------------------------------------------------------
def http_json(url: str, data: Optional[dict] = None, token: Optional[str] = None) -> dict:
    """GET (or form POST when `data` is given); errors raise HTTPError with Google's JSON body as `.body`."""
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode() if data is not None else None)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            e.body = json.loads(e.read() or b"{}")
        except ValueError:
            e.body = {}
        raise


def parse_duration(iso: str) -> int:
    """YouTube's ISO 8601 duration ("PT1H2M3S", "P1DT2S") in seconds."""
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + s


# --- account -----------------------------------------------------------------------------
class GoogleAccount:
    def __init__(self, client: dict, db, http: Callable = http_json):
        self.client = client
        self._db = db
        self._http = http
        self._access: Tuple[str, float] = ("", 0.0)  # token, expiry (monotonic)

    @property
    def connected(self) -> bool:
        return bool(self._db.get_setting(TOKEN_KEY, ""))

    def start_sign_in(self) -> dict:
        """Ask Google for a code to show: {user_code, verification_url, device_code, interval, expires_in}."""
        return self._http(DEVICE_CODE, data={"client_id": self.client["client_id"], "scope": SCOPE})

    def finish_sign_in(self, start: dict, cancel: Optional[threading.Event] = None):
        """Wait for the user to enter the code at google.com/device; save the sign-in. Raises SignedOut."""
        cancel = cancel or threading.Event()
        interval = start.get("interval", 5)
        deadline = time.monotonic() + start.get("expires_in", 1800)
        while time.monotonic() < deadline:
            if cancel.wait(interval):
                raise SignedOut("cancelled")
            try:
                tokens = self._http(self.client["token_uri"], data={
                    "client_id": self.client["client_id"], "client_secret": self.client.get("client_secret", ""),
                    "device_code": start["device_code"], "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                })
            except urllib.error.HTTPError as e:
                error = getattr(e, "body", {}).get("error")
                if error == "authorization_pending":
                    continue
                if error == "slow_down":
                    interval += 5
                    continue
                raise SignedOut("you said no" if error == "access_denied" else error or str(e)) from e
            self._db.set_setting(TOKEN_KEY, encrypt(tokens["refresh_token"]))
            self._access = (tokens["access_token"], time.monotonic() + tokens.get("expires_in", 3600) - 60)
            return
        raise SignedOut("the code expired")

    def sign_out(self):
        stored = self._db.get_setting(TOKEN_KEY, "")
        self._db.set_setting(TOKEN_KEY, "")
        self._access = ("", 0.0)
        if stored:
            try:  # best effort: also tell Google to forget it
                self._http(REVOKE, data={"token": decrypt(stored)})
            except Exception:
                pass

    def _token(self) -> str:
        token, expiry = self._access
        if token and time.monotonic() < expiry:
            return token
        stored = self._db.get_setting(TOKEN_KEY, "")
        if not stored:
            raise SignedOut("not connected")
        try:
            got = self._http(self.client["token_uri"], data={
                "refresh_token": decrypt(stored), "client_id": self.client["client_id"],
                "client_secret": self.client.get("client_secret", ""), "grant_type": "refresh_token",
            })
        except urllib.error.HTTPError as e:
            if getattr(e, "body", {}).get("error") == "invalid_grant":  # revoked, or the 7-day testing limit
                self._db.set_setting(TOKEN_KEY, "")
                raise SignedOut("Google sign-in expired") from e
            raise
        self._access = (got["access_token"], time.monotonic() + got.get("expires_in", 3600) - 60)
        return self._access[0]

    def _items(self, path: str, **params) -> List[dict]:
        """Every item of a paged YouTube API list."""
        items, page = [], None
        while True:
            q = dict(params, maxResults=50, **({"pageToken": page} if page else {}))
            data = self._http(API + path + "?" + urllib.parse.urlencode(q), token=self._token())
            items += data.get("items", [])
            page = data.get("nextPageToken")
            if not page:
                return items

    @staticmethod
    def _music(videos: List[dict]) -> Tuple[List[Track], int]:
        """The songs among these videos (YouTube category "Music"), and how many videos are playable at all.

        Private videos (even your own) can't be played without browser cookies, so they don't count.
        """
        playable = [v for v in videos if v.get("status", {}).get("privacyStatus") != "private"]
        songs = []
        for v in playable:
            s = v.get("snippet", {})
            if s.get("categoryId") == MUSIC:
                songs.append(Track(video_id=v["id"], title=s.get("title") or v["id"],
                                   channel=s.get("channelTitle") or "Unknown Artist",
                                   duration_sec=parse_duration(v.get("contentDetails", {}).get("duration", ""))))
        return songs, len(playable)

    def _videos(self, ids: List[str]) -> List[dict]:
        """Details for these video ids, in order; deleted ones don't come back from the API."""
        found = {}
        for i in range(0, len(ids), 50):
            for v in self._items("videos", part="snippet,contentDetails,status", id=",".join(ids[i:i + 50])):
                found[v["id"]] = v
        return [found[i] for i in ids if i in found]

    def playlists(self) -> List[Tuple[str, str]]:
        """(id, title) of the user's own playlists, private ones included."""
        return [(p["id"], p["snippet"]["title"]) for p in self._items("playlists", part="snippet", mine="true")]

    def playlist_tracks(self, playlist_id: str) -> Tuple[List[Track], int]:
        """(songs in the playlist, number of playable videos in it). A playlist YouTube can't find counts as empty."""
        try:
            items = self._items("playlistItems", part="contentDetails", playlistId=playlist_id)
        except urllib.error.HTTPError as e:
            if e.code != 404:  # e.g. deleted while syncing, or a list YouTube won't return through the API
                raise
            return [], 0
        return self._music(self._videos([it["contentDetails"]["videoId"] for it in items]))

    def liked(self) -> Tuple[List[Track], int]:
        return self._music(self._items("videos", part="snippet,contentDetails,status", myRating="like"))
