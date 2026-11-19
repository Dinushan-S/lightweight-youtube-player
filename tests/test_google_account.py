"""Ticket 08: Google device-flow sign-in, encrypted token storage, authenticated playlist sync."""
import threading
import urllib.error
import urllib.parse

import pytest

from src.player.controller import PlayerController
from src.player.database import DatabaseManager
from src.player.google_account import (DEVICE_CODE, TOKEN_KEY, GoogleAccount, SignedOut, decrypt, load_client,
                                       parse_duration)
from tests.test_controller import MockAudioEngine, MockResolver

CLIENT = {"client_id": "cid", "client_secret": "sec", "auth_uri": "https://auth.test/o",
          "token_uri": "https://token.test/t"}


class FakeGoogle:
    """Stands in for Google's token endpoint and the YouTube Data API."""

    def __init__(self, answers=("authorization_pending", "authorization_pending", None)):
        self.posts = []
        self.playlists = {"PL1": ("Deep Work", ["a", "b", "gone", "mine"]), "PL2": ("Old", ["a"]),
                          "PL3": ("AI_learn", ["talk", "talk2", "a"])}  # mostly not music: left out
        self.refresh_ok = True
        self.answers = list(answers)  # what the token endpoint says to each poll; None = the user entered the code

    @staticmethod
    def _error(url, code):
        err = urllib.error.HTTPError(url, 428, code, {}, None)
        err.body = {"error": code}
        return err

    def __call__(self, url, data=None, token=None):
        if data is not None:
            self.posts.append((url, data))
            if url == DEVICE_CODE:
                return {"device_code": "DEV", "user_code": "ABCD-EFGH", "verification_url": "https://www.google.com/device",
                        "interval": 0, "expires_in": 5}
            if data.get("grant_type", "").endswith("device_code"):
                answer = self.answers.pop(0) if self.answers else "authorization_pending"
                if answer:
                    raise self._error(url, answer)
                return {"access_token": "AT", "refresh_token": "RT-secret", "expires_in": 3600}
            if data.get("grant_type") == "refresh_token":
                if not self.refresh_ok:
                    raise self._error(url, "invalid_grant")
                return {"access_token": "AT2", "expires_in": 3600}
            return {}
        assert token in ("AT", "AT2"), "API called without a valid access token"
        u = urllib.parse.urlparse(url)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        path = u.path.rsplit("/", 1)[-1]
        if path == "playlists":  # PLX is listed but its items 404 (deleted mid-sync): skipped, not fatal
            return {"items": [{"id": k, "snippet": {"title": t}} for k, (t, _) in self.playlists.items()]
                    + [{"id": "PLX", "snippet": {"title": "Gone"}}]}
        if path == "playlistItems":
            if q["playlistId"] not in self.playlists:
                raise urllib.error.HTTPError(url, 404, "playlistNotFound", {}, None)
            ids = self.playlists[q["playlistId"]][1]
            half = None if q.get("pageToken") else "p2"  # two pages
            part = ids[2:] if q.get("pageToken") else ids[:2]
            return {"items": [{"contentDetails": {"videoId": i}} for i in part], "nextPageToken": half}
        if path == "videos" and q.get("myRating") == "like":
            return {"items": [self._video("z"), self._video("talk")]}
        if path == "videos":
            return {"items": [self._video(i) for i in q["id"].split(",") if i != "gone"]}  # deleted: not returned
        raise AssertionError(url)

    @staticmethod
    def _video(vid):
        return {"id": vid, "snippet": {"title": f"T-{vid}", "channelTitle": "Ch",
                                       "categoryId": "28" if vid.startswith("talk") else "10"},  # 10 = Music
                "contentDetails": {"duration": "PT3M5S"},
                "status": {"privacyStatus": "private" if vid == "mine" else "public"}}


def test_device_flow_polls_until_code_entered_and_stores_token_encrypted():
    db, fake = DatabaseManager(db_path=":memory:"), FakeGoogle()
    acct = GoogleAccount(CLIENT, db, http=fake)
    assert not acct.connected
    start = acct.start_sign_in()
    assert start["user_code"] == "ABCD-EFGH" and fake.posts[0][1]["scope"].endswith("youtube.readonly")
    acct.finish_sign_in(start)

    polls = [d for u, d in fake.posts if u == CLIENT["token_uri"]]
    assert len(polls) == 3 and all(d["device_code"] == "DEV" and d["client_secret"] == "sec" for d in polls)
    stored = db.get_setting(TOKEN_KEY)
    assert "RT-secret" not in stored and decrypt(stored) == "RT-secret"  # saved encrypted (DPAPI)
    assert GoogleAccount(CLIENT, db, http=fake).connected  # survives a restart


@pytest.mark.parametrize("answers,cancel", [(("access_denied",), False), ((), True)])
def test_refused_or_cancelled_sign_in_does_not_connect(answers, cancel):
    db = DatabaseManager(db_path=":memory:")
    acct = GoogleAccount(CLIENT, db, http=FakeGoogle(answers))
    stop = threading.Event()
    if cancel:
        stop.set()
    with pytest.raises(SignedOut):
        acct.finish_sign_in(acct.start_sign_in(), stop)
    assert not acct.connected


def test_connect_shows_code_then_syncs():
    db, fake = DatabaseManager(db_path=":memory:"), FakeGoogle()
    ctrl = PlayerController(engine=MockAudioEngine(), resolver=MockResolver(), db=db,
                            google_client=CLIENT, google_http=fake)
    codes, done = [], threading.Event()
    result = []
    ctrl.connect_google_async(on_code=lambda c, u: codes.append((c, u)),
                              on_complete=lambda ok, msg: (result.append((ok, msg)), done.set()))
    assert done.wait(5)
    assert codes == [("ABCD-EFGH", "https://www.google.com/device")]
    assert result == [(True, "Google: 3 playlists synced")] and ctrl.google_connected


def _connected_controller():
    db, fake = DatabaseManager(db_path=":memory:"), FakeGoogle()
    ctrl = PlayerController(engine=MockAudioEngine(), resolver=MockResolver(), db=db,
                            google_client=CLIENT, google_http=fake)
    ctrl._google.finish_sign_in(ctrl._google.start_sign_in())
    return ctrl, db, fake


def test_sync_fetches_playlists_and_liked_videos_through_controller():
    ctrl, db, fake = _connected_controller()
    assert ctrl.google_available and ctrl.google_connected
    assert ctrl.sync_google() == 3

    pls = {p["id"]: p for p in ctrl.get_playlists()}
    assert pls["google-PL1"]["title"] == "Deep Work" and pls["google-PL1"]["source_type"] == "google"
    deep = db.get_playlist_tracks("google-PL1")
    assert [t.video_id for t in deep] == ["a", "b"]  # paged, order kept; deleted + private left out
    assert deep[0].duration_sec == 185 and deep[0].channel == "Ch"
    assert "google-PL3" not in pls  # 1 song in 3 videos: not a music playlist
    assert pls["google-LL"]["title"] == "Liked music"
    assert [t.video_id for t in db.get_playlist_tracks("google-LL")] == ["z"]  # liked talk video left out
    assert ctrl.play_playlist("google-PL1")

    del fake.playlists["PL2"]  # deleted on YouTube: dropped on the next sync, own playlists untouched
    own = ctrl.create_playlist("Mine")
    ctrl.sync_google()
    ids = {p["id"] for p in ctrl.get_playlists()}
    assert "google-PL2" not in ids and {"google-PL1", "google-LL", own} <= ids


def test_expired_sign_in_disconnects_and_disconnect_removes_synced_playlists():
    ctrl, db, fake = _connected_controller()
    ctrl.sync_google()
    ctrl._google._access = ("", 0.0)  # access token used up: next call must refresh
    fake.refresh_ok = False
    with pytest.raises(SignedOut):
        ctrl.sync_google()
    assert not ctrl.google_connected

    own = ctrl.create_playlist("Mine")
    ctrl.disconnect_google()
    assert [p["id"] for p in ctrl.get_playlists()] == [own]


def test_no_client_file_means_no_google_and_duration_parsing(tmp_path):
    assert load_client(str(tmp_path)) is None
    assert not PlayerController(engine=MockAudioEngine(), resolver=MockResolver(),
                                db=DatabaseManager(db_path=":memory:")).google_available
    (tmp_path / "client_secret_x.json").write_text('{"installed": {"client_id": "id1"}}')
    assert load_client(str(tmp_path))["client_id"] == "id1"
    assert [parse_duration(s) for s in ("PT3M5S", "PT1H", "P1DT2S", "", "junk")] == [185, 3600, 86402, 0, 0]
