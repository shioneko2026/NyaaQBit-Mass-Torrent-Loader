"""
qBittorrent Web API wrapper for Mass Torrent Loader.
All public methods return (success: bool, message: str) tuples — never raise.
"""

import qbittorrentapi


class QBitClient:
    def __init__(self, host="localhost", port=8080, username="admin", password="adminadmin"):
        self.client = qbittorrentapi.Client(
            host=host,
            port=port,
            username=username,
            password=password,
        )

    def test_connection(self):
        """Test connection and auth. Returns (ok, message)."""
        try:
            self.client.auth_log_in()
            version = self.client.app.version
            return True, f"Connected — qBittorrent {version}"
        except qbittorrentapi.LoginFailed:
            return False, "Login failed — check username and password."
        except qbittorrentapi.APIConnectionError:
            return False, (
                "Cannot connect. Make sure qBittorrent is running and "
                "Web UI is enabled (Tools > Options > Web UI)."
            )
        except Exception as e:
            return False, f"Unexpected error: {e}"

    def get_categories(self):
        """Return list of category names. Empty list on failure."""
        try:
            cats = self.client.torrent_categories.categories
            return sorted(cats.keys())
        except Exception:
            return []

    def get_category_details(self):
        """Return {name: save_path} dict for all categories."""
        try:
            cats = self.client.torrent_categories.categories
            return {name: cat.savePath for name, cat in cats.items()}
        except Exception:
            return {}

    def add_torrent(self, file_path, category="", save_path="", paused=False):
        """
        Add a single .torrent file.
        Returns (status, message) where status is one of: "ok", "skip", "error".
        """
        try:
            with open(file_path, "rb") as f:
                torrent_data = f.read()
        except OSError as e:
            return "error", f"Cannot read file: {e}"

        try:
            result = self.client.torrents_add(
                torrent_files=torrent_data,
                category=category or None,
                save_path=save_path or None,
                is_paused=paused,
            )
            if result == "Ok.":
                return "ok", "Added successfully"
            else:
                return "skip", "Already exists or rejected by qBittorrent"
        except qbittorrentapi.Conflict409Error:
            return "skip", "Already exists in qBittorrent"
        except Exception as e:
            return "error", f"{e}"

    def get_paused_torrents(self, category=""):
        """Get info hashes of paused torrents in a category."""
        try:
            torrents = self.client.torrents_info(
                status_filter="paused",
                category=category or None,
            )
            return [t.hash for t in torrents]
        except Exception:
            return []

    def resume_torrents(self, hashes):
        """Resume a list of torrents by hash. Returns (ok, message)."""
        try:
            self.client.torrents_resume(torrent_hashes=hashes)
            return True, f"Resumed {len(hashes)} torrent(s)"
        except Exception as e:
            return False, f"Resume failed: {e}"
