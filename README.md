# applemusic_to_spotify

Small utility to convert an Apple Music export into Spotify playlists.

## What this repository contains

- `applemusic_to_spotify.py` — main script that parses an Apple Music export and creates Spotify playlists.
- `tests/` — pytest-based unit tests for parsing and Spotify-related logic (uses mocks).
- `.env.example` — example environment variables file.
- `.env` — local environment file (should contain your real Spotify credentials). This file is ignored by git via `.gitignore`.
- `requirements.txt` — Python dependencies.

## Requirements

- Python 3.8+ (this project was tested with the system Python available here).
- A Spotify developer application (Client ID, Client Secret, Redirect URI).

## Quick start (recommended)

1. Create a virtual environment and install dependencies (from project root):

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

2. Create your `.env` file from the example and fill in real credentials:

```sh
cp .env.example .env
# then edit .env and set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET
```

3. Optionally update other settings in `.env` (INPUT_FILE, redirect URI, etc.).

4. Run tests:

```sh
# with the virtualenv active
pytest -q tests
# or explicitly with the venv pytest binary
./.venv/bin/pytest -q tests
```

5. Run the script (with venv active):

```sh
python applemusic_to_spotify.py
```

The script will read configuration from environment variables (loaded from `.env` by `python-dotenv`). If environment variables are missing, the script will fall back to sensible defaults defined in the code (e.g. `music_export.txt` input file).

## Notes

- Do NOT commit your `.env` file — it contains secrets. The repo includes `.gitignore` with `.env` added.
- Tests are written to avoid network calls by mocking Spotify interactions.
- If you want me to run the tests here, I can run them inside the created `.venv` and report results.

## Troubleshooting

- If your editor shows unresolved import warnings, make sure the `.venv` interpreter is selected in your editor or install dependencies in your active environment.
- If Spotify OAuth prompts are required, ensure your `SPOTIFY_REDIRECT_URI` matches what you've configured in the Spotify Developer Dashboard.
