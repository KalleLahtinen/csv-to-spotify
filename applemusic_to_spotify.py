import json
import csv
import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

# -----------------------------
# CONFIGURATION (load from environment / .env)
# -----------------------------
load_dotenv()

# If an environment variable is not set, fall back to the existing default
INPUT_FILE = os.getenv("INPUT_FILE", "music_export.txt")  # Output from AppleScript
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "YOUR_SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "YOUR_SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")
SCOPE = os.getenv("SPOTIFY_SCOPE", "playlist-modify-private playlist-modify-public")
MISSING_TRACKS_FILE = os.getenv("MISSING_TRACKS_FILE", "missing_tracks.csv")
JSON_EXPORT_FILE = os.getenv("JSON_EXPORT_FILE", "music_export.json")

# -----------------------------
# STEP 1: Parse Apple Music Export
# -----------------------------
def parse_music_export(file_path):
    playlists = {}
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) == 4:
                playlist_name, title, artist, album = parts
                if playlist_name not in playlists:
                    playlists[playlist_name] = []
                playlists[playlist_name].append({
                    "title": title,
                    "artist": artist,
                    "album": album
                })
    return playlists

# -----------------------------
# STEP 2: Spotify Authentication
# -----------------------------
def authenticate_spotify():
    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE
    ))

# -----------------------------
# STEP 3: Track Search Logic
# -----------------------------
def search_track(sp, title, artist=None):
    if not title or title.lower() == "unknown":
        return None

    query = f'track:{title}' + (f' artist:{artist}' if artist and artist.lower() != "unknown" else "")
    try:
        result = sp.search(q=query, type="track", limit=1)
        if result["tracks"]["items"]:
            return result["tracks"]["items"][0]["uri"]

        # Fallback: search by title only
        fallback_result = sp.search(q=f'track:{title}', type="track", limit=1)
        if fallback_result["tracks"]["items"]:
            return fallback_result["tracks"]["items"][0]["uri"]
    except Exception as e:
        print(f"Error searching track '{title}': {e}")
    return None

# -----------------------------
# STEP 4: Create Playlists & Add Tracks
# -----------------------------
def create_spotify_playlists(sp, user_id, playlists):
    missing_tracks = []

    for playlist_name, tracks in playlists.items():
        print(f"\nCreating playlist: {playlist_name}")
        playlist = sp.user_playlist_create(user=user_id, name=playlist_name, public=False)
        playlist_id = playlist["id"]

        track_uris = []
        for track in tracks:
            uri = search_track(sp, track["title"], track["artist"])
            if uri:
                track_uris.append(uri)
                print(f"✔ Found: {track['title']} by {track['artist']}")
            else:
                missing_tracks.append({
                    "playlist": playlist_name,
                    "title": track["title"],
                    "artist": track["artist"],
                    "reason": "Not found or title unknown"
                })
                print(f"✖ Missing: {track['title']} by {track['artist']}")

        # Add tracks in batches of 100
        for i in range(0, len(track_uris), 100):
            sp.playlist_add_items(playlist_id, track_uris[i:i+100])

    # Export missing tracks
    with open(MISSING_TRACKS_FILE, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["playlist", "title", "artist", "reason"])
        writer.writeheader()
        writer.writerows(missing_tracks)

    print(f"\n✅ All playlists processed! Missing tracks logged to {MISSING_TRACKS_FILE}")

# -----------------------------
# MAIN EXECUTION
# -----------------------------
if __name__ == "__main__":
    playlists = parse_music_export(INPUT_FILE)

    # Save JSON for reference
    with open(JSON_EXPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(playlists, f, indent=2)

    sp = authenticate_spotify()
    user_id = sp.current_user()["id"]

    create_spotify_playlists(sp, user_id, playlists)