"""
Config Manager for Mass Torrent Loader
Handles JSON config/preset storage for connection settings and presets.
"""

import json
import os
import sys


def _get_config_dir():
    """Get the directory where config.json lives."""
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))

    config_path = os.path.join(base, "config.json")
    if os.access(base, os.W_OK):
        return base

    fallback = os.path.join(os.environ.get("APPDATA", ""), "MassTorrentLoader")
    os.makedirs(fallback, exist_ok=True)
    return fallback


CONFIG_PATH = os.path.join(_get_config_dir(), "config.json")

DEFAULT_CONFIG = {
    "connection": {
        "host": "localhost",
        "port": 8080,
        "username": "admin",
        "password": "adminadmin",
    },
    "presets": {},
    "options": {
        "delay": 1.0,
        "paused_mode": False,
        "batch_size": 5,
    },
    "last_used": {
        "preset": "",
        "browse_dir": "",
        "rss_category": "",
    },
}


def load_config():
    """Load config from disk, merging with defaults for any missing keys."""
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONFIG)

    merged = _deep_merge(DEFAULT_CONFIG, data)
    return merged


def save_config(config):
    """Write config to disk."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def _deep_merge(defaults, override):
    """Merge override into defaults, keeping any extra keys from override."""
    result = dict(defaults)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


# --- Preset helpers ---

def get_presets(config):
    """Return dict of presets: {name: {category, save_path}}."""
    return config.get("presets", {})


def add_preset(config, name, category, save_path):
    """Add or update a preset. Returns updated config."""
    config.setdefault("presets", {})[name] = {
        "category": category,
        "save_path": save_path,
    }
    save_config(config)
    return config


def delete_preset(config, name):
    """Delete a preset by name. Returns updated config."""
    config.get("presets", {}).pop(name, None)
    save_config(config)
    return config


# --- Connection helpers ---

def get_connection(config):
    """Return connection dict."""
    return config.get("connection", DEFAULT_CONFIG["connection"])


def set_connection(config, host, port, username, password):
    """Update connection settings. Returns updated config."""
    config["connection"] = {
        "host": host,
        "port": int(port),
        "username": username,
        "password": password,
    }
    save_config(config)
    return config


# --- Options helpers ---

def get_options(config):
    """Return options dict."""
    return config.get("options", DEFAULT_CONFIG["options"])


def set_options(config, delay, paused_mode, batch_size):
    """Update options. Returns updated config."""
    config["options"] = {
        "delay": float(delay),
        "paused_mode": bool(paused_mode),
        "batch_size": int(batch_size),
    }
    save_config(config)
    return config
