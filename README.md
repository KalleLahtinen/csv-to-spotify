# CSV Export to Spotify Playlist Converter

This script converts CSV playlist exports into Spotify playlists. It handles encoding issues, rate limits, and provides detailed logging and export options.

## Features

- **CSV Export Parsing**: Supports semicolon-delimited files by default, with customizable delimiters.
- **Encoding Fallback**: Automatically detects and handles encodings (`utf-8`, `cp1252`, `latin-1`), with a fallback to `utf-8` with replacement for undecodable bytes.
- **Spotify Playlist Creation**: Authenticates with Spotify and creates playlists with tracks from the parsed export.
- **Rate Limit Handling**: Detects and respects Spotify API rate limits, with optional logging of rate-limit events.
- **Export Options**:
  - Timestamped JSON export (e.g., `playlist_export_2025-11-16_12-34-56Z.json`).
  - No duplicate "latest" file; the timestamped file is the primary export.
- **Interactive Confirmation**: Optionally prompts for confirmation before uploading playlists to Spotify.
- **Command-Line Flags**:
  - `--delimiter`: Specify the delimiter used in the export file.
  - `--export-only`: Parse and export playlists without uploading to Spotify.
  - `--verbose`: Print detailed diagnostics (e.g., encoding, delimiter, playlist counts).
  - `--confirm`: Skip confirmation prompts and proceed directly to upload.
  - `--stop-on-429`: Stop execution on the first rate-limit event.
  - `--rate-log-file`: Specify a file to log rate-limit events.

## Requirements

- Python 3.8+
- Spotify Developer Account (for API credentials)
- CSV playlist export file

## Setup

1. Clone the repository:
   ```sh
   git clone <repository-url>
   cd applemusic_to_spotify
   ```

2. Create and activate a virtual environment:
   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```

4. Create a `.env` file with your Spotify API credentials:
   ```env
   SPOTIFY_CLIENT_ID=your_client_id
   SPOTIFY_CLIENT_SECRET=your_client_secret
   SPOTIFY_REDIRECT_URI=http://localhost:8888/callback
   ```

## Usage

### Basic Usage

1. Export your playlists to a CSV file (e.g., `playlist_export.csv`).
2. Run the script:
   ```sh
   python export_to_spotify.py --input playlist_export.csv
   ```

### Advanced Options

- Specify a custom delimiter:
  ```sh
  python export_to_spotify.py --input playlist_export.csv --delimiter "|"
  ```

- Export playlists without uploading:
  ```sh
  python export_to_spotify.py --input playlist_export.csv --export-only
  ```

- Enable verbose diagnostics:
  ```sh
  python export_to_spotify.py --input playlist_export.csv --verbose
  ```

- Skip confirmation prompts:
  ```sh
  python export_to_spotify.py --input playlist_export.csv --confirm
  ```

- Stop on the first rate-limit event:
  ```sh
  python export_to_spotify.py --input playlist_export.csv --stop-on-429
  ```

- Log rate-limit events to a specific file:
  ```sh
  python export_to_spotify.py --input playlist_export.csv --rate-log-file rate_limit_log.jsonl
  ```

## Testing

Run the test suite with:
```sh
pytest
```

## Notes

- Spotify does not require unique playlist names, so the script will always create a new playlist with the given name even if a similar one already exists.
- The script creates a timestamped JSON export of parsed playlists. This file can be reviewed before uploading.
- If undecodable bytes are encountered, they are replaced with the Unicode replacement character (`�`).
- Ensure your Spotify Developer credentials are correctly set in the `.env` file.

## Disclaimer

This project was created with the assistance of Visual Studio Code Agents.  
While efforts have been made to ensure functionality and accuracy, the code may contain errors or limitations.  
Use this project at your own discretion and risk. The author assumes no liability for any issues arising from its use.

## License

This project is licensed under the MIT License.
