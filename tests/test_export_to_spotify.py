import os
import importlib

import pytest

import export_to_spotify as exs
from pathlib import Path
import json


def test_parse_music_export(tmp_path):
    data = (
        "MyPlaylist | Song A | Artist A | Album A\n"
        "OtherPlaylist | Song B | Artist B | Album B\n"
        "MyPlaylist | Song C | Artist C | Album C\n"
    )
    f = tmp_path / "export.txt"
    f.write_text(data, encoding="utf-8")

    playlists = exs.parse_music_export(str(f), delimiter="|")

    assert "MyPlaylist" in playlists
    assert len(playlists["MyPlaylist"]) == 2
    assert playlists["MyPlaylist"][0]["title"] == "Song A"
    assert playlists["OtherPlaylist"][0]["artist"] == "Artist B"


def test_search_track_found_and_fallback():
    class MockSpFound:
        def search(self, q, type, limit):
            return {"tracks": {"items": [{"uri": "spotify:track:123"}]}}

    uri = exs.search_track(MockSpFound(), "Song A", "Artist A")
    assert uri == "spotify:track:123"

    class MockSpFallback:
        def __init__(self):
            self.calls = 0

        def search(self, q, type, limit):
            # First call: no results, second call: returns result
            if self.calls == 0:
                self.calls += 1
                return {"tracks": {"items": []}}
            return {"tracks": {"items": [{"uri": "spotify:track:456"}]}}

    uri2 = exs.search_track(MockSpFallback(), "Song B", "Artist B")
    assert uri2 == "spotify:track:456"


def test_search_track_no_title():
    # None or empty or 'unknown' should return None
    assert exs.search_track(None, "", None) is None
    assert exs.search_track(None, None, None) is None
    assert exs.search_track(None, "unknown", "Artist") is None


def test_create_spotify_playlists_records_missing_and_adds_tracks(tmp_path, monkeypatch):
    # Create a small playlists structure
    playlists = {
        "MyList": [
            {"title": "FoundSong", "artist": "A"},
            {"title": "MissingSong", "artist": "B"},
        ]
    }

    # Mock Spotify client
    class MockSp:
        def __init__(self):
            self.created = []
            self.added = []

        def user_playlist_create(self, user, name, public):
            self.created.append((user, name, public))
            return {"id": "pl_1"}

        def playlist_add_items(self, playlist_id, uris):
            # record added items
            self.added.append((playlist_id, tuple(uris)))

    sp = MockSp()

    # Monkeypatch the search_track function in the module to control results
    def fake_search_track(sp_obj, title, artist=None):
        if title == "FoundSong":
            return "spotify:track:found"
        return None

    monkeypatch.setattr(exs, "search_track", fake_search_track)

    # Redirect missing tracks file to a temp path
    tmp_missing = tmp_path / "missing.csv"
    monkeypatch.setattr(exs, "MISSING_TRACKS_FILE", str(tmp_missing))

    exs.create_spotify_playlists(sp, "testuser", playlists)

    # Verify playlist creation
    assert sp.created and sp.created[0][1] == "MyList"

    # Verify that the found track was added
    assert sp.added and sp.added[0][1] == ("spotify:track:found",)

    # Verify missing file contains the missing track title
    content = tmp_missing.read_text(encoding="utf-8")
    assert "MissingSong" in content


def test_create_json_export_from_test_file(tmp_path, monkeypatch):
    """Verify the script can parse the bundled test_export_300.csv and save a JSON export."""
    data_path = Path(exs.__file__).parent / "test_export_300.csv"
    assert data_path.exists(), f"test file not found at {data_path}"

    playlists = exs.parse_music_export(str(data_path))
    assert isinstance(playlists, dict)
    assert playlists, "parsed playlists should not be empty"

    out = tmp_path / "export.json"
    # monkeypatch module constant and perform the same save behavior as main
    monkeypatch.setattr(exs, "JSON_EXPORT_FILE", str(out))

    with open(exs.JSON_EXPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(playlists, f, indent=2)

    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded == playlists
