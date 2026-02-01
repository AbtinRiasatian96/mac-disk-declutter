"""Filesystem scanning logic."""

import os
import subprocess
import time
from datetime import datetime
from pathlib import Path


def human_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def get_dir_size(path: Path) -> int:
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False):
                    total += get_dir_size(Path(entry.path))
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass
    return total


def get_item_count(path: Path) -> int:
    count = 0
    try:
        for entry in os.scandir(path):
            count += 1
    except (PermissionError, OSError):
        pass
    return count


def get_last_modified(path: Path) -> str:
    try:
        mtime = path.stat().st_mtime
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
    except (OSError, ValueError):
        return "unknown"


def get_homebrew_cache() -> str | None:
    try:
        result = subprocess.run(
            ["brew", "--cache"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def scan_location(path_str: str, category: str) -> list[dict]:
    """Scan a single location and return items found."""
    path = Path(os.path.expanduser(path_str))
    if not path.exists():
        return []

    items = []

    # Directories to always break down into top-level children
    EXPAND_DIRS = {"Downloads", ".Trash", "Movies", "steamapps"}

    if path.name in EXPAND_DIRS:
        # List individual top-level items with age info
        try:
            for entry in sorted(os.scandir(path), key=lambda e: e.stat(follow_symlinks=False).st_mtime):
                try:
                    ep = Path(entry.path)
                    if entry.is_file(follow_symlinks=False):
                        size = entry.stat(follow_symlinks=False).st_size
                    else:
                        size = get_dir_size(ep)
                    items.append({
                        "path": str(ep),
                        "name": entry.name,
                        "size": size,
                        "size_human": human_size(size),
                        "type": "folder" if entry.is_dir() else "file",
                        "category": category,
                        "last_modified": get_last_modified(ep),
                        "parent": str(path),
                        "item_count": get_item_count(ep) if entry.is_dir() else 1,
                    })
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            pass
    elif category == "review" and "MobileSync" in path_str:
        # Show individual backups with dates
        try:
            for entry in os.scandir(path):
                if entry.is_dir():
                    ep = Path(entry.path)
                    size = get_dir_size(ep)
                    items.append({
                        "path": str(ep),
                        "name": f"iOS Backup: {entry.name}",
                        "size": size,
                        "size_human": human_size(size),
                        "type": "folder",
                        "category": category,
                        "last_modified": get_last_modified(ep),
                        "parent": str(path),
                        "item_count": get_item_count(ep),
                    })
        except (PermissionError, OSError):
            pass
    else:
        # Aggregate: show subfolders as groups
        size = get_dir_size(path)
        if size < 1024:  # Skip near-empty
            return []
        sub_items = get_item_count(path)

        # For large directories, show per-subfolder breakdown
        BREAKDOWN_DIRS = {
            "Caches", "DerivedData", "Archives", "iOS DeviceSupport",
            "watchOS DeviceSupport", "tvOS DeviceSupport", "CoreSimulator",
            "CacheStorage", "CachedData", "Cache", "caches", "repository",
        }
        if path.name in BREAKDOWN_DIRS or sub_items > 3:
            try:
                for entry in os.scandir(path):
                    if entry.is_dir():
                        ep = Path(entry.path)
                        s = get_dir_size(ep)
                        if s > 1_000_000:  # Only show > 1MB
                            items.append({
                                "path": str(ep),
                                "name": f"{entry.name} cache",
                                "size": s,
                                "size_human": human_size(s),
                                "type": "folder",
                                "category": category,
                                "last_modified": get_last_modified(ep),
                                "parent": str(path),
                                "item_count": get_item_count(ep),
                            })
            except (PermissionError, OSError):
                pass
            # If no large sub-items found, show the whole folder
            if not items:
                items.append({
                    "path": str(path),
                    "name": path.name,
                    "size": size,
                    "size_human": human_size(size),
                    "type": "folder",
                    "category": category,
                    "last_modified": get_last_modified(path),
                    "parent": str(path.parent),
                    "item_count": sub_items,
                })
        else:
            items.append({
                "path": str(path),
                "name": path.name,
                "size": size,
                "size_human": human_size(size),
                "type": "folder",
                "category": category,
                "last_modified": get_last_modified(path),
                "parent": str(path.parent),
                "item_count": sub_items,
            })

    return items


def scan_all(config: dict) -> list[dict]:
    """Scan all configured locations and return aggregated items."""
    locations = config.get("scan_locations", {})
    all_items = []

    # Check for homebrew cache
    brew_cache = get_homebrew_cache()
    safe_locs = list(locations.get("safe", []))
    if brew_cache and brew_cache not in safe_locs:
        safe_locs.append(brew_cache)

    for path_str in safe_locs:
        all_items.extend(scan_location(path_str, "safe"))

    for path_str in locations.get("review", []):
        all_items.extend(scan_location(path_str, "review"))

    for path_str in locations.get("personal", []):
        all_items.extend(scan_location(path_str, "personal"))

    # Sort by ROI: size * safety_weight (safe=1.0, review=0.6, personal=0.3)
    weight = {"safe": 1.0, "review": 0.6, "personal": 0.3}
    all_items.sort(key=lambda x: x["size"] * weight.get(x["category"], 0.5), reverse=True)

    return all_items
