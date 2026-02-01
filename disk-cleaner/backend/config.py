"""Configuration management for disk-cleaner."""

import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".disk-cleaner"
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_LOG = CONFIG_DIR / "history.log"

DEFAULT_CONFIG = {
    "llm_provider": "claude",  # "claude" or "ollama"
    "claude_api_key": "",
    "claude_model": "claude-sonnet-4-20250514",
    "ollama_model": "llama3",
    "ollama_url": "http://localhost:11434",
    "scan_locations": {
        "safe": [
            "~/Library/Caches",
            "~/Library/Logs",
            "~/Library/Developer/Xcode/DerivedData",
            "~/Library/Developer/Xcode/Archives",
            "~/Library/Developer/Xcode/iOS DeviceSupport",
            "~/Library/Developer/Xcode/watchOS DeviceSupport",
            "~/Library/Developer/Xcode/tvOS DeviceSupport",
            "~/.npm/_cacache",
            "~/Library/Caches/pip",
            "~/.cargo/registry/cache",
            "~/.gradle/caches",
            "~/.m2/repository",
            "~/Library/Containers/com.docker.docker/Data/vms",
            "~/Library/Group Containers/group.com.docker/cache",
            "~/.cocoapods/repos",
            "~/Library/Saved Application State",
            "~/Library/Caches/com.spotify.client/Data",
            "/private/var/folders",
            "~/.cache",
        ],
        "review": [
            "~/Library/Developer/CoreSimulator",
            "~/Library/Application Support/MobileSync/Backup",
            "~/Library/Mail/V*/MailData/Envelope Index-shm",
            "~/Library/Messages/Attachments",
            "~/Library/Application Support/Slack/Service Worker/CacheStorage",
            "~/Library/Application Support/discord/Cache",
            "~/Library/Application Support/Google/Chrome/Default/Service Worker/CacheStorage",
            "~/Library/Application Support/Code/CachedData",
            "~/Library/Application Support/Code/Cache",
            "~/Library/Application Support/Code/CachedExtensionVSIXs",
        ],
        "personal": [
            "~/Downloads",
            "~/.Trash",
            "~/Library/Application Support/Steam/steamapps",
            "~/Movies",
        ],
    },
}


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    ensure_config_dir()
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            saved = json.load(f)
        # Merge with defaults
        merged = {**DEFAULT_CONFIG, **saved}
        return merged
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    ensure_config_dir()
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def log_deletion(path: str, method: str):
    ensure_config_dir()
    import datetime
    with open(HISTORY_LOG, "a") as f:
        f.write(f"{datetime.datetime.now().isoformat()} | {method} | {path}\n")
