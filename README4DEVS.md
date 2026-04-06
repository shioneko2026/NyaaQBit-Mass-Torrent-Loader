> For the user-facing README, see [README.md](README.md).

## Tech Stack & Dependencies

- **Language:** Python 3.x
- **GUI:** tkinter (stdlib) + tkinterdnd2 (drag-and-drop)
- **qBittorrent integration:** qbittorrent-api
- **RSS parsing:** feedparser
- **HTTP:** requests

Install via `install_dependencies.bat` or `pip install -r requirements.txt`.

---

## Project Structure

| File | Purpose |
|---|---|
| `mass_torrent_loader.py` | Entry point — main app class and UI |
| `qbit_client.py` | qBittorrent Web API wrapper |
| `rss_fetcher.py` | RSS feed fetching and smart folder name extraction |
| `config_manager.py` | Config load/save |
| `config.json` | Runtime config (auto-generated, not in git) |
| `config.example.json` | Config template with defaults |
| `run.bat` | Launcher |
| `install_dependencies.bat` | Installs pip dependencies |

---

## How to Run from Source

1. Install Python 3.x — add to PATH
2. Run `install_dependencies.bat` or `pip install -r requirements.txt`
3. Run `run.bat` or `python mass_torrent_loader.py`
4. Enter qBittorrent Web UI credentials on first launch and click Test

**qBittorrent prerequisite:** Web UI must be enabled — Tools → Options → Web UI → check "Web User Interface (Remote Control)".

---

## Config Reference

Stored in `config.json` next to the script. Falls back to `%APPDATA%\MassTorrentLoader\` if the directory is read-only.

| Key | Default | Description |
|---|---|---|
| `connection.host` | `localhost` | qBittorrent Web UI host |
| `connection.port` | `8080` | qBittorrent Web UI port |
| `connection.username` | `admin` | Web UI username |
| `connection.password` | `adminadmin` | Web UI password (plaintext) |
| `options.delay` | `1.0` | Seconds between torrent additions |
| `options.paused_mode` | `false` | Add all as paused, resume in groups |
| `options.batch_size` | `5` | Batch size for paused mode resuming |
| `presets` | `{}` | Saved category/path combinations |
| `last_used.rss_category` | `""` | Last RSS category, persisted between sessions |

---

## Architecture Notes

**Threading:** File loading and RSS fetching run on background threads to keep the UI responsive. Each operation gets a `threading.Event` (`cancel_event`, `rss_cancel_event`) for clean cancellation.

**tkinterdnd2:** Replaces the standard `Tk()` root with `TkinterDnD.Tk()`. If you modify root window initialization, preserve this — reverting to plain `Tk()` silently breaks drag-and-drop.

**Smart folder naming:** `rss_fetcher.extract_smart_name()` parses nyaa.si filenames with regex to extract show title, quality tag, and release group. It's tuned for nyaa.si conventions and will produce garbage on non-standard filenames — failures fall back to the raw title rather than crashing.

**Auto-connect:** The app attempts a qBittorrent connection 100ms after launch using saved credentials. If it fails, the UI stays functional — the error shows in the connection status label.

---

## Known Issues & Technical Debt

- Credentials stored in plaintext in `config.json` — acceptable for a local tool
- Paused batch mode is implemented but undertested
- RSS smart naming is regex-based and nyaa.si-specific — other sources need their own parser
- No retry logic on failed torrent additions — failed adds are logged but not retried
