# Mass Torrent Loader (MTL)

A Windows GUI application that bulk-loads .torrent files into qBittorrent via the Web API, with controlled pacing to prevent the "moving" status issue that occurs when adding many torrents at once.

## Limitations

- **qBittorrent only** — uses the qBittorrent Web API directly. Deluge, Transmission, and other clients are not supported.
- **RSS tab is nyaa.si only** — the feed parsing, torrent downloading, and smart folder naming are built specifically around nyaa.si's RSS format. Other RSS sources will not work correctly.

## Features

**File Loader tab**
- Select .torrent files via Windows file picker (multi-select, sortable by date) or drag-and-drop from Explorer
- Assign a category and save path, with category list pulled from qBittorrent
- Save presets for frequently used category/path combinations
- Configurable delay between additions (default 1.0s) to prevent qBittorrent's "moving" status on large batches
- Optional paused batch mode: add all as paused, then resume in groups

**RSS Feed tab**
- Paste a nyaa.si RSS URL and fetch the feed
- Selectable checklist of all entries, sorted alphabetically
- Smart folder naming: extracts title, quality tags, and group from filenames (e.g. `[ASW] Hell Mode - 12 [1080p HEVC x265 10Bit][AAC]` → `Hell Mode [1080p HEVC x265 10Bit] - [ASW]`)
- Category auto-fills the save path from qBittorrent; folder name is editable
- Remembers the last category used between sessions

## Requirements

- Python 3.x
- qBittorrent with Web UI enabled (default port 8080)
- Windows (uses Windows-specific DPI awareness and tkinterdnd2)

## Setup

1. Enable qBittorrent Web UI: **Tools > Options > Web UI > check "Web User Interface (Remote Control)"**
2. Note your Web UI port, username, and password
3. Clone or download this repo
4. Run `install_dependencies.bat` (first time only)
5. Run the app via `run.bat`
6. On first launch, enter your qBittorrent host, port, and credentials in the Connection section and click **Test**

> Your credentials are saved to `config.json` locally and are not tracked by git.

## Configuration

The app saves settings to `config.json` next to the executable (or `%APPDATA%\MassTorrentLoader\` if the directory is read-only). A `config.example.json` is included showing the structure and default values.

## Dependencies

```
qbittorrent-api
tkinterdnd2
feedparser
requests
```

Install all at once with `install_dependencies.bat` or:

```
pip install -r requirements.txt
```
