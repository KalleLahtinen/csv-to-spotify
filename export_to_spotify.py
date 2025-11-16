import json
import csv
import os
import re
import time
import argparse
import datetime
import sys
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

# -----------------------------
# CONFIGURATION (load from environment / .env)
# -----------------------------
load_dotenv()

# If an environment variable is not set, fall back to the existing default
INPUT_FILE = os.getenv("INPUT_FILE", "playlist_export.csv")  # Source data csv file
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "YOUR_SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "YOUR_SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")
SCOPE = os.getenv("SPOTIFY_SCOPE", "playlist-modify-private playlist-modify-public")
MISSING_TRACKS_FILE = os.getenv("MISSING_TRACKS_FILE", "missing_tracks.csv")
JSON_EXPORT_FILE = os.getenv("JSON_EXPORT_FILE", "playlist_export.json")
RATE_LIMIT_LOG = os.getenv("RATE_LIMIT_LOG", "rate_limit_events.jsonl")
STOP_ON_FIRST_RATE_LIMIT = os.getenv("STOP_ON_FIRST_RATE_LIMIT", "true").lower() in ("1", "true", "yes")

# -----------------------------
# STEP 1: Parse CSV Export
# -----------------------------
def parse_playlist_export(file_path, delimiter=None, return_meta=False):
    """Parse the CSV export file into a dict of playlists.

    This function attempts to read the input file using several common
    encodings to avoid UnicodeDecodeError on files produced on Windows
    or with legacy encodings. If necessary it will fall back to UTF-8
    with errors='replace' so the script can continue and bad characters
    are replaced.
    """
    def _read_lines_with_fallback(path):
        encodings = ["utf-8", "cp1252", "latin-1"]
        for enc in encodings:
            try:
                with open(path, "r", encoding=enc) as fh:
                    return fh.readlines(), enc, False
            except UnicodeDecodeError:
                # try next encoding
                continue
            except Exception:
                # other I/O errors should propagate
                raise

        # Last resort: read with utf-8 but replace invalid bytes so we don't crash
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            print(f"Warning: input file {path} contained undecodable bytes; some characters were replaced.")
            return fh.readlines(), "utf-8-replace", True

    playlists = {}
    lines, used_encoding, replaced = _read_lines_with_fallback(file_path)

    # Determine delimiter: use explicit parameter, then environment, then default to ';'
    if delimiter is None:
        delimiter = os.getenv("INPUT_DELIMITER", ";")

    for line in lines:
        parts = [p.strip() for p in line.split(delimiter)]
        if len(parts) == 4:
            playlist_name, title, artist, album = parts
            if playlist_name not in playlists:
                playlists[playlist_name] = []
            playlists[playlist_name].append({
                "title": title,
                "artist": artist,
                "album": album
            })
    if return_meta:
        meta = {"encoding": used_encoding, "replaced": replaced, "delimiter": delimiter, "playlists_count": len(playlists)}
        return playlists, meta
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


def _get_retry_after_from_exception(exc):
    """Try to extract a Retry-After value (seconds) from a Spotify/requests exception.

    Returns int seconds or None.
    """
    # Common places for headers
    headers = None
    if hasattr(exc, "headers") and isinstance(exc.headers, dict):
        headers = exc.headers
    elif hasattr(exc, "response") and getattr(exc.response, "headers", None):
        headers = exc.response.headers

    if headers:
        for key in ("Retry-After", "retry-after"):
            if key in headers:
                try:
                    return int(headers[key])
                except Exception:
                    pass

    # Some Spotify exceptions expose http_status or status
    status = getattr(exc, "http_status", None) or getattr(exc, "status", None)
    if status == 429:
        # No header present; let caller decide backoff
        return None

    # Try to find a "Retry-After: <seconds>" in the string representation
    m = re.search(r"retry-?after\D*(\d+)", str(exc), flags=re.I)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            pass

    return None


def spotify_call(func, *args, max_retries=5, backoff_factor=1, **kwargs):
    """Call a Spotify API function and respect rate limit (HTTP 429) responses.

    If a 429 is encountered, this will sleep for the server-provided Retry-After
    seconds when available, otherwise use exponential backoff. After max_retries
    it will re-raise the last exception.
    """
    attempt = 0
    while True:
        try:
            # Extract special internal-only kwargs that should not be forwarded to the
            # underlying Spotify function (e.g. logging context).
            rl_context = None
            if "_rl_context" in kwargs:
                rl_context = kwargs.pop("_rl_context")

            return func(*args, **kwargs)
        except Exception as exc:
            attempt += 1
            # Try to detect a Retry-After header or 429 status
            retry_after = _get_retry_after_from_exception(exc)

            is_rate_limit = False
            # If we found a retry_after header or the exception text/status hints 429
            if retry_after is not None:
                is_rate_limit = True
            else:
                # Look for HTTP 429 hint in exception attributes or text
                status = getattr(exc, "http_status", None) or getattr(exc, "status", None)
                if status == 429 or re.search(r"\b429\b", str(exc)):
                    is_rate_limit = True

            if not is_rate_limit or attempt > max_retries:
                # Not a rate-limit or we've retried enough
                raise

            # Log the rate-limit event for analysis
            try:
                event = {
                    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                    "function": getattr(func, "__name__", str(func)),
                    "args_summary": _summarize_args(args, kwargs),
                    "attempt": attempt,
                    "max_retries": max_retries,
                    "retry_after_header": retry_after,
                    "exception_str": str(exc),
                }
                if rl_context:
                    try:
                        event["context"] = rl_context
                    except Exception:
                        pass
                _log_rate_limit_event(event)
            except Exception:
                # Do not let logging errors hide the root exception
                pass

            # Decide how long to wait
            if retry_after is not None:
                wait = int(retry_after) + 1
            else:
                # exponential backoff
                wait = backoff_factor * (2 ** (attempt - 1))

            print(f"Rate limit encountered. Sleeping for {wait} seconds (attempt {attempt}/{max_retries})...")
            time.sleep(wait)

            # If configured to stop on first (observed) rate limit, raise a specific exception
            if STOP_ON_FIRST_RATE_LIMIT:
                raise RateLimitCaptured("Rate limit encountered and STOP_ON_FIRST_RATE_LIMIT is true")


def _summarize_args(args, kwargs):
    """Create a safe, small summary of args/kwargs for logging (avoid secrets)."""
    try:
        args_s = []
        for a in args:
            if isinstance(a, (str, int, float)):
                args_s.append(str(a)[:200])
            else:
                args_s.append(type(a).__name__)

        kw_s = {}
        for k, v in kwargs.items():
            if k.lower() in ("client_secret", "authorization", "token", "auth", "headers"):
                kw_s[k] = "<redacted>"
            elif isinstance(v, (str, int, float)):
                kw_s[k] = str(v)[:200]
            else:
                kw_s[k] = type(v).__name__

        return {"args": args_s, "kwargs": kw_s}
    except Exception:
        return {"args": [], "kwargs": {}}


def _log_rate_limit_event(event, file_path=None):
    """Append a JSON line with the rate-limit event to the configured file."""
    if file_path is None:
        file_path = RATE_LIMIT_LOG
    # Ensure directory exists
    try:
        dirp = os.path.dirname(file_path)
        if dirp:
            os.makedirs(dirp, exist_ok=True)
    except Exception:
        pass

    with open(file_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


class RateLimitCaptured(Exception):
    """Raised when a rate limit is captured and STOP_ON_FIRST_RATE_LIMIT is true."""
    pass

# -----------------------------
# STEP 3: Track Search Logic
# -----------------------------
def search_track(sp, title, artist=None):
    if not title or title.lower() == "unknown":
        return None

    query = f'track:{title}' + (f' artist:{artist}' if artist and artist.lower() != "unknown" else "")
    try:
        result = spotify_call(sp.search, q=query, type="track", limit=1)
        if result["tracks"]["items"]:
            return result["tracks"]["items"][0]["uri"]

        # Fallback: search by title only
        fallback_result = spotify_call(sp.search, q=f'track:{title}', type="track", limit=1)
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
        # attach a small context so logs show which playlist we were creating
        try:
            playlist = spotify_call(sp.user_playlist_create, user=user_id, name=playlist_name, public=False, _rl_context={"playlist": playlist_name})
        except RateLimitCaptured:
            print("Stopped due to captured rate limit while creating playlist.")
            raise
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
            try:
                spotify_call(sp.playlist_add_items, playlist_id, track_uris[i:i+100], _rl_context={"playlist": playlist_name, "batch_index": i})
            except RateLimitCaptured:
                print("Stopped due to captured rate limit while adding tracks.")
                raise

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
    parser = argparse.ArgumentParser(description="Convert CSV export to Spotify playlists (with rate-limit capture support)")
    parser.add_argument("--input", "-i", default=INPUT_FILE, help="Path to CSV export file (default from env)")
    parser.add_argument("--delimiter", "-d", default=None, help="Delimiter used in the export file (default ';' or INPUT_DELIMITER env)")
    parser.add_argument("--export-only", dest="export_only", action="store_true", help="Only parse input and write JSON export, do not upload to Spotify")
    parser.add_argument("--verbose", dest="verbose", action="store_true", help="Print diagnostics about encoding, delimiter and parsed counts")
    parser.add_argument("--confirm", dest="confirm", action="store_true", help="Skip interactive confirmation and proceed with uploading to Spotify")
    parser.add_argument("--stop-on-429", dest="stop_on_429", action="store_true", help="Stop and save rate-limit info on first observed 429")
    parser.add_argument("--rate-log-file", dest="rate_log_file", default=RATE_LIMIT_LOG, help="File to append rate-limit events (default: rate_limit_events.jsonl)")
    args = parser.parse_args()

    # Override runtime flags from CLI
    if args.stop_on_429:
        STOP_ON_FIRST_RATE_LIMIT = True
    if args.rate_log_file:
        RATE_LIMIT_LOG = args.rate_log_file

    if args.verbose:
        playlists, meta = parse_playlist_export(args.input, delimiter=args.delimiter, return_meta=True)
        print(f"Parsed {meta['playlists_count']} playlists using encoding={meta['encoding']} (replaced={meta['replaced']}) delimiter='{meta['delimiter']}'")
    else:
        playlists = parse_playlist_export(args.input, delimiter=args.delimiter)

    # Save JSON for reference. Write a timestamped file as the primary export
    # (more human-readable timestamp) and optionally keep a non-timestamped
    # "latest" copy for compatibility. Timestamp uses UTC timezone.
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d_%H-%M-%SZ")
    def _timestamped_path(path, ts):
        base, ext = os.path.splitext(path)
        if not ext:
            ext = ".json"
        return f"{base}_{ts}{ext}"

    timestamped = _timestamped_path(JSON_EXPORT_FILE, ts)
    # write timestamped primary file (only copy)
    with open(timestamped, "w", encoding="utf-8") as f:
        json.dump(playlists, f, indent=2)

    export_path = timestamped
    if args.verbose:
        print(f"Saved timestamped JSON export to {export_path}")

    if args.export_only:
        print(f"Exported parsed playlists to {export_path}. Exiting (export-only mode).")
        raise SystemExit(0)

    # If confirmation not explicitly provided, pretty-print a summary and ask the user
    def pretty_print_summary(playlists, limit=10):
        total_playlists = len(playlists)
        total_tracks = sum(len(v) for v in playlists.values())
        print(f"\nSummary: {total_playlists} playlists, {total_tracks} total tracks")
        print("Top playlists (name — tracks):")
        shown = 0
        for name, tracks in playlists.items():
            print(f" - {name} — {len(tracks)}")
            shown += 1
            if shown >= limit:
                break

    if not args.confirm:
        pretty_print_summary(playlists)
        # If stdin is not a tty, require explicit --confirm to avoid hanging in CI
        if not sys.stdin.isatty():
            print("Non-interactive environment detected. To proceed with upload, re-run with --confirm.")
            raise SystemExit(2)

        resp = input("Proceed to upload these playlists to Spotify? [y/N]: ").strip().lower()
        if resp not in ("y", "yes"):
            print("Aborting upload.")
            raise SystemExit(0)

    start_time = time.time()  # Start the timer

    sp = authenticate_spotify()
    try:
        user_id = spotify_call(sp.current_user)["id"]
    except RateLimitCaptured:
        print("Rate limit captured while fetching current user. Check the rate-limit log.")
        raise

    try:
        create_spotify_playlists(sp, user_id, playlists)
    except RateLimitCaptured:
        print(f"A rate limit was captured. Details were appended to {RATE_LIMIT_LOG}")

    end_time = time.time()  # End the timer
    elapsed_time = end_time - start_time
    print(f"\n✅ All playlists processed in {elapsed_time:.2f} seconds!")