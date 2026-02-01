"""Filesystem scanning logic."""

import glob as globmod
import os
import subprocess
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


def _make_item(path: Path, name: str, size: int, category: str, type_: str = "folder",
               parent: str | None = None, item_count: int | None = None,
               tag: str | None = None) -> dict:
    """Helper to build a scan result dict."""
    item = {
        "path": str(path),
        "name": name,
        "size": size,
        "size_human": human_size(size),
        "type": type_,
        "category": category,
        "last_modified": get_last_modified(path),
        "parent": parent or str(path.parent),
        "item_count": item_count if item_count is not None else (get_item_count(path) if path.is_dir() else 1),
    }
    if tag:
        item["tag"] = tag
    return item


def scan_location(path_str: str, category: str) -> list[dict]:
    """Scan a single location and return items found."""
    path = Path(os.path.expanduser(path_str))
    if not path.exists():
        return []

    items = []

    # Directories to always break down into top-level children
    EXPAND_DIRS = {"Downloads", ".Trash", "Movies", "steamapps"}

    if path.name in EXPAND_DIRS:
        try:
            for entry in sorted(os.scandir(path), key=lambda e: e.stat(follow_symlinks=False).st_mtime):
                try:
                    ep = Path(entry.path)
                    if entry.is_file(follow_symlinks=False):
                        size = entry.stat(follow_symlinks=False).st_size
                    else:
                        size = get_dir_size(ep)
                    items.append(_make_item(
                        ep, entry.name, size, category,
                        type_="folder" if entry.is_dir() else "file",
                        parent=str(path),
                    ))
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            pass
    elif category == "review" and "MobileSync" in path_str:
        try:
            for entry in os.scandir(path):
                if entry.is_dir():
                    ep = Path(entry.path)
                    size = get_dir_size(ep)
                    items.append(_make_item(
                        ep, f"iOS Backup: {entry.name}", size, category,
                        parent=str(path),
                    ))
        except (PermissionError, OSError):
            pass
    else:
        size = get_dir_size(path)
        if size < 1024:
            return []
        sub_items = get_item_count(path)

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
                        if s > 1_000_000:
                            items.append(_make_item(
                                ep, f"{entry.name} cache", s, category,
                                parent=str(path),
                            ))
            except (PermissionError, OSError):
                pass
            if not items:
                items.append(_make_item(path, path.name, size, category,
                                        parent=str(path.parent), item_count=sub_items))
        else:
            items.append(_make_item(path, path.name, size, category,
                                    parent=str(path.parent), item_count=sub_items))

    return items


# --- Deep scan: node_modules, .git, large log files ---

def _find_node_modules(base_dirs: list[str]) -> list[dict]:
    """Find node_modules directories under project dirs."""
    results = []
    seen = set()
    for dir_str in base_dirs:
        base = Path(os.path.expanduser(dir_str))
        if not base.exists():
            continue
        for root, dirs, _files in os.walk(base, followlinks=False):
            # Don't recurse into node_modules or .git
            dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "__pycache__", ".venv", "venv")]
            nm = Path(root) / "node_modules"
            if nm.is_dir() and str(nm) not in seen:
                seen.add(str(nm))
                try:
                    size = get_dir_size(nm)
                    if size > 1_000_000:  # >1MB
                        project_name = Path(root).name
                        results.append(_make_item(
                            nm, f"node_modules ({project_name})", size, "safe",
                            parent=root, tag="node_modules",
                        ))
                except (PermissionError, OSError):
                    continue
    return results


def _find_large_git(base_dirs: list[str], min_bytes: int = 500_000_000) -> list[dict]:
    """Find .git directories over a size threshold."""
    results = []
    seen = set()
    for dir_str in base_dirs:
        base = Path(os.path.expanduser(dir_str))
        if not base.exists():
            continue
        for root, dirs, _files in os.walk(base, followlinks=False):
            dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__", ".venv", "venv")]
            git_dir = Path(root) / ".git"
            if git_dir.is_dir() and str(git_dir) not in seen:
                seen.add(str(git_dir))
                dirs[:] = [d for d in dirs if d != ".git"]  # don't recurse into .git
                try:
                    size = get_dir_size(git_dir)
                    if size > min_bytes:
                        project_name = Path(root).name
                        results.append(_make_item(
                            git_dir, f".git ({project_name}) — consider git gc", size, "review",
                            parent=root, tag="large_git",
                        ))
                except (PermissionError, OSError):
                    continue
    return results


def _find_log_files(base_dirs: list[str], min_bytes: int = 10_000_000) -> list[dict]:
    """Find *.log files over a threshold in project dirs."""
    results = []
    seen = set()
    for dir_str in base_dirs:
        base = Path(os.path.expanduser(dir_str))
        if not base.exists():
            continue
        for root, dirs, files in os.walk(base, followlinks=False):
            dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "__pycache__", ".venv", "venv")]
            for f in files:
                if f.endswith(".log"):
                    fp = Path(root) / f
                    if str(fp) in seen:
                        continue
                    seen.add(str(fp))
                    try:
                        size = fp.stat().st_size
                        if size > min_bytes:
                            results.append(_make_item(
                                fp, f, size, "safe",
                                type_="file", parent=root, tag="log_file",
                            ))
                    except (PermissionError, OSError):
                        continue
    return results


def _find_large_files(min_bytes: int, extensions: list[str]) -> list[dict]:
    """Scan home directory for files > min_bytes with certain extensions."""
    results = []
    home = Path.home()
    skip_dirs = {
        "Library", ".Trash", "node_modules", ".git", "__pycache__",
        ".venv", "venv", ".cargo", ".rustup", ".gradle", ".m2",
    }
    ext_set = set(extensions)

    for root, dirs, files in os.walk(home, followlinks=False):
        # Skip system/hidden dirs at top level and always skip certain dirs
        rel = Path(root).relative_to(home)
        dirs[:] = [d for d in dirs if d not in skip_dirs and not (
            rel == Path(".") and d.startswith(".") and d not in (".Trash",)
        )]
        for f in files:
            fp = Path(root) / f
            # Check extension (handle .tar.gz etc)
            matches = any(f.endswith(ext) for ext in ext_set)
            if not matches:
                continue
            try:
                size = fp.stat(follow_symlinks=False).st_size
                if size >= min_bytes:
                    results.append(_make_item(
                        fp, f, size, "personal",
                        type_="file", parent=root, tag="large_file",
                    ))
            except (PermissionError, OSError):
                continue
    return results


def _find_container_caches() -> list[dict]:
    """Scan ~/Library/Containers/*/Data/Library/Caches for app sandbox caches."""
    results = []
    containers = Path.home() / "Library" / "Containers"
    if not containers.exists():
        return results
    try:
        for entry in os.scandir(containers):
            if not entry.is_dir():
                continue
            cache_dir = Path(entry.path) / "Data" / "Library" / "Caches"
            if cache_dir.is_dir():
                size = get_dir_size(cache_dir)
                if size > 5_000_000:  # >5MB
                    app_name = entry.name.split(".")[-1] if "." in entry.name else entry.name
                    results.append(_make_item(
                        cache_dir, f"{app_name} container cache", size, "safe",
                        parent=str(containers), tag="container_cache",
                    ))
    except (PermissionError, OSError):
        pass
    return results


def scan_all(config: dict, deep: bool = False) -> list[dict]:
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

    # Container caches (glob pattern)
    all_items.extend(_find_container_caches())

    if deep:
        deep_dirs = config.get("deep_scan_dirs", [])
        all_items.extend(_find_node_modules(deep_dirs))
        all_items.extend(_find_large_git(deep_dirs))
        all_items.extend(_find_log_files(deep_dirs))

        min_bytes = config.get("large_file_min_bytes", 500_000_000)
        extensions = config.get("large_file_extensions", [])
        all_items.extend(_find_large_files(min_bytes, extensions))

    # Sort by ROI: size * safety_weight (safe=1.0, review=0.6, personal=0.3)
    weight = {"safe": 1.0, "review": 0.6, "personal": 0.3}
    all_items.sort(key=lambda x: x["size"] * weight.get(x["category"], 0.5), reverse=True)

    return all_items
