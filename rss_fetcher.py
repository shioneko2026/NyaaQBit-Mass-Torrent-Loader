"""
RSS Feed parser and .torrent downloader for Mass Torrent Loader.
Handles nyaa.si RSS feeds, smart folder name extraction, and torrent file downloads.
"""

import os
import re
import tempfile

import feedparser
import requests


def fetch_feed(url):
    """
    Parse an RSS feed URL and return entries.
    Returns (ok, result) where result is a list of dicts or an error string.
    Each dict: {title, download_url, size}
    """
    try:
        feed = feedparser.parse(url)
    except Exception as e:
        return False, f"Failed to parse feed: {e}"

    if feed.bozo and not feed.entries:
        return False, f"Invalid feed: {feed.bozo_exception}"

    if not feed.entries:
        return False, "Feed is empty — no entries found."

    entries = []
    for item in feed.entries:
        title = item.get("title", "Unknown")
        download_url = item.get("link", "")
        size = ""

        # nyaa-specific size tag
        if hasattr(item, "nyaa_size"):
            size = item.nyaa_size
        elif hasattr(item, "nyaa_size"):
            size = item.nyaa_size

        entries.append({
            "title": title,
            "download_url": download_url,
            "size": size,
        })

    return True, entries


def extract_smart_name(titles):
    """
    Extract a smart folder name from a list of RSS entry titles.

    Input:  ["[ASW] Hell Mode - 12 [1080p HEVC x265 10Bit][AAC]", ...]
    Output: "Hell Mode [1080p HEVC x265 10Bit][AAC] - [ASW]"

    Logic: move [Group] from front to back, strip episode number.
    """
    if not titles:
        return ""

    title = titles[0]

    # Step 1: Extract leading [Group] tag
    group = ""
    group_match = re.match(r'^\[([^\]]+)\]\s*', title)
    if group_match:
        group = group_match.group(1)
        title = title[group_match.end():]

    # Step 2: Strip episode number patterns
    # Matches: " - 01", " - 12", " - 01v2", " Episode 01", " Ep01", " E01"
    title = re.sub(r'\s*-\s*\d+(?:v\d+)?\s*', ' ', title)
    title = re.sub(r'\s*(?:Episode|Ep\.?|E)\s*\d+(?:v\d+)?\s*', ' ', title, flags=re.IGNORECASE)

    # Step 3: Clean up extra whitespace
    title = re.sub(r'\s+', ' ', title).strip()

    # Step 4: Append group to the back
    if group:
        name = f"{title} - [{group}]"
    else:
        name = title

    return name


def download_torrent(download_url, dest_folder=None):
    """
    Download a .torrent file from a URL.
    Returns (ok, file_path_or_error).
    """
    if dest_folder is None:
        dest_folder = tempfile.mkdtemp(prefix="mtl_")

    os.makedirs(dest_folder, exist_ok=True)

    try:
        resp = requests.get(download_url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        return False, f"Download failed: {e}"

    # Derive filename from URL or content-disposition
    filename = None
    cd = resp.headers.get("content-disposition", "")
    if "filename=" in cd:
        match = re.search(r'filename="?([^";\n]+)"?', cd)
        if match:
            filename = match.group(1).strip()

    if not filename:
        # Derive from URL path
        url_path = download_url.rstrip("/").split("/")[-1]
        if url_path.endswith(".torrent"):
            filename = url_path
        else:
            filename = f"{url_path}.torrent"

    # Sanitize filename
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)

    filepath = os.path.join(dest_folder, filename)
    try:
        with open(filepath, "wb") as f:
            f.write(resp.content)
    except OSError as e:
        return False, f"Cannot save file: {e}"

    return True, filepath
