"""Filesystem scanning logic."""

import glob as globmod
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Generator


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
               tag: str | None = None, section: str = "known") -> dict:
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
        "section": section,
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
    results = []
    seen = set()
    for dir_str in base_dirs:
        base = Path(os.path.expanduser(dir_str))
        if not base.exists():
            continue
        for root, dirs, _files in os.walk(base, followlinks=False):
            dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "__pycache__", ".venv", "venv")]
            nm = Path(root) / "node_modules"
            if nm.is_dir() and str(nm) not in seen:
                seen.add(str(nm))
                try:
                    size = get_dir_size(nm)
                    if size > 1_000_000:
                        project_name = Path(root).name
                        results.append(_make_item(
                            nm, f"node_modules ({project_name})", size, "safe",
                            parent=root, tag="node_modules",
                        ))
                except (PermissionError, OSError):
                    continue
    return results


def _find_large_git(base_dirs: list[str], min_bytes: int = 500_000_000) -> list[dict]:
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
                dirs[:] = [d for d in dirs if d != ".git"]
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
    results = []
    home = Path.home()
    skip_dirs = {
        "Library", ".Trash", "node_modules", ".git", "__pycache__",
        ".venv", "venv", ".cargo", ".rustup", ".gradle", ".m2",
    }
    ext_set = set(extensions)

    for root, dirs, files in os.walk(home, followlinks=False):
        rel = Path(root).relative_to(home)
        dirs[:] = [d for d in dirs if d not in skip_dirs and not (
            rel == Path(".") and d.startswith(".") and d not in (".Trash",)
        )]
        for f in files:
            fp = Path(root) / f
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
                if size > 5_000_000:
                    app_name = entry.name.split(".")[-1] if "." in entry.name else entry.name
                    results.append(_make_item(
                        cache_dir, f"{app_name} container cache", size, "safe",
                        parent=str(containers), tag="container_cache",
                    ))
    except (PermissionError, OSError):
        pass
    return results


# --- Full home directory size crawler ("Find Space Hogs") ---

def _get_top_level_dirs_with_size(base: Path, skip: set[str]) -> list[tuple[Path, int]]:
    """Get immediate children of base with their total sizes, skipping named dirs."""
    results = []
    try:
        for entry in os.scandir(base):
            if not entry.is_dir(follow_symlinks=False):
                continue
            if entry.name in skip:
                continue
            try:
                size = get_dir_size(Path(entry.path))
                results.append((Path(entry.path), size))
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass
    return results


def discover_space_hogs(min_bytes: int = 100_000_000, top_n: int = 50,
                        progress_callback=None) -> list[dict]:
    """Crawl ~/ to find the top N largest directories (>min_bytes).

    Uses a two-pass approach:
    1. Scan top-level dirs under ~/ to get coarse sizes
    2. For large ones, drill into children to find the actual hogs

    progress_callback(phase, current, total, message) is called for progress updates.
    """
    home = Path.home()
    # Dirs to skip entirely (system, already covered by known scan)
    skip_top = {".Trash", ".cache", ".npm", ".cargo", ".rustup", ".gradle",
                ".m2", ".cocoapods", ".pub-cache", ".gem", ".nuget", "go"}

    # Phase 1: size top-level dirs
    if progress_callback:
        progress_callback("crawl", 0, 1, "Measuring top-level directories...")

    top_dirs = []
    try:
        entries = list(os.scandir(home))
    except (PermissionError, OSError):
        entries = []

    total_entries = len(entries)
    for i, entry in enumerate(entries):
        if not entry.is_dir(follow_symlinks=False):
            continue
        if entry.name in skip_top:
            continue
        if progress_callback:
            progress_callback("crawl", i + 1, total_entries, f"Sizing ~/{entry.name}...")
        try:
            size = get_dir_size(Path(entry.path))
            if size >= min_bytes:
                top_dirs.append((Path(entry.path), size))
        except (PermissionError, OSError):
            continue

    # Phase 2: for each large dir, drill into children
    all_hogs: list[tuple[Path, int]] = []
    # Also include Library subdirs which are often huge
    library = home / "Library"
    if library.exists():
        if progress_callback:
            progress_callback("drill", 0, 1, "Drilling into ~/Library...")
        lib_children = _get_top_level_dirs_with_size(library, set())
        for p, s in lib_children:
            if s >= min_bytes:
                all_hogs.append((p, s))

    drill_dirs = [(p, s) for p, s in top_dirs if p.name != "Library"]
    for i, (dir_path, dir_size) in enumerate(drill_dirs):
        if progress_callback:
            progress_callback("drill", i + 1, len(drill_dirs),
                              f"Drilling into ~/{dir_path.name}...")
        # Get children
        children = _get_top_level_dirs_with_size(dir_path, {"node_modules", ".git", "__pycache__"})
        large_children = [(p, s) for p, s in children if s >= min_bytes]
        if large_children:
            all_hogs.extend(large_children)
        else:
            # No large children individually — show the dir itself
            all_hogs.append((dir_path, dir_size))

    # Also find large individual files anywhere under ~/
    if progress_callback:
        progress_callback("files", 0, 1, "Scanning for large files (>500MB)...")
    large_file_exts = {
        ".iso", ".dmg", ".zip", ".tar.gz", ".tgz", ".tar.bz2",
        ".mov", ".mp4", ".avi", ".mkv", ".pkg", ".rar", ".7z",
        ".vmdk", ".vdi", ".qcow2", ".ova", ".docker", ".img",
    }
    large_files: list[tuple[Path, int]] = []
    skip_walk = {"node_modules", ".git", "__pycache__", ".venv", "venv"}
    for root, dirs, files in os.walk(home, followlinks=False):
        dirs[:] = [d for d in dirs if d not in skip_walk]
        for f in files:
            if any(f.endswith(ext) for ext in large_file_exts):
                fp = Path(root) / f
                try:
                    size = fp.stat(follow_symlinks=False).st_size
                    if size >= 500_000_000:  # 500MB
                        large_files.append((fp, size))
                except (PermissionError, OSError):
                    continue

    # Deduplicate: remove hogs that are parents/children of each other, keep deepest
    all_hogs.sort(key=lambda x: len(str(x[0])), reverse=True)  # deepest first
    seen_paths: set[str] = set()
    deduped: list[tuple[Path, int]] = []
    # Collect all known-scan paths to exclude from discovered section
    # (these are already shown in the "Known Safe Items" section)

    for p, s in all_hogs:
        sp = str(p)
        # Skip if a child path is already included
        if any(sp.startswith(seen) or seen.startswith(sp) for seen in seen_paths):
            continue
        seen_paths.add(sp)
        deduped.append((p, s))

    # Sort by size descending, take top N
    deduped.sort(key=lambda x: x[1], reverse=True)
    deduped = deduped[:top_n]

    # Convert to items
    items = []
    for p, s in deduped:
        # Categorize heuristically
        sp = str(p)
        if "Cache" in sp or "cache" in sp or "Logs" in sp or "logs" in sp or "DerivedData" in sp:
            cat = "safe"
        elif "Library" in sp:
            cat = "review"
        else:
            cat = "review"  # discovered items default to review
        items.append(_make_item(
            p, p.name, s, cat, section="discovered", tag="space_hog",
            parent=str(p.parent),
        ))

    # Add large files
    for p, s in large_files:
        items.append(_make_item(
            p, p.name, s, "personal", type_="file",
            section="discovered", tag="large_file", parent=str(p.parent),
        ))

    items.sort(key=lambda x: x["size"], reverse=True)
    return items[:top_n]


def scan_all(config: dict, deep: bool = False) -> list[dict]:
    """Scan all configured locations and return aggregated items."""
    locations = config.get("scan_locations", {})
    all_items = []

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

    all_items.extend(_find_container_caches())

    if deep:
        deep_dirs = config.get("deep_scan_dirs", [])
        all_items.extend(_find_node_modules(deep_dirs))
        all_items.extend(_find_large_git(deep_dirs))
        all_items.extend(_find_log_files(deep_dirs))

        min_bytes = config.get("large_file_min_bytes", 500_000_000)
        extensions = config.get("large_file_extensions", [])
        all_items.extend(_find_large_files(min_bytes, extensions))

    weight = {"safe": 1.0, "review": 0.6, "personal": 0.3}
    all_items.sort(key=lambda x: x["size"] * weight.get(x["category"], 0.5), reverse=True)

    return all_items


def scan_all_streaming(config: dict, deep: bool = False) -> Generator[str, None, None]:
    """Like scan_all but yields SSE events for progress updates.

    Yields lines in SSE format: "data: {json}\n\n"
    Final event has type "done" with full results.
    """
    def sse(data: dict) -> str:
        return f"data: {json.dumps(data)}\n\n"

    yield sse({"type": "progress", "phase": "known", "message": "Scanning known locations..."})

    locations = config.get("scan_locations", {})
    known_items = []

    brew_cache = get_homebrew_cache()
    safe_locs = list(locations.get("safe", []))
    if brew_cache and brew_cache not in safe_locs:
        safe_locs.append(brew_cache)

    total_locs = len(safe_locs) + len(locations.get("review", [])) + len(locations.get("personal", []))
    scanned = 0

    for path_str in safe_locs:
        scanned += 1
        yield sse({"type": "progress", "phase": "known", "current": scanned, "total": total_locs,
                    "message": f"Scanning {path_str}..."})
        known_items.extend(scan_location(path_str, "safe"))

    for path_str in locations.get("review", []):
        scanned += 1
        yield sse({"type": "progress", "phase": "known", "current": scanned, "total": total_locs,
                    "message": f"Scanning {path_str}..."})
        known_items.extend(scan_location(path_str, "review"))

    for path_str in locations.get("personal", []):
        scanned += 1
        yield sse({"type": "progress", "phase": "known", "current": scanned, "total": total_locs,
                    "message": f"Scanning {path_str}..."})
        known_items.extend(scan_location(path_str, "personal"))

    yield sse({"type": "progress", "phase": "known", "message": "Scanning container caches..."})
    known_items.extend(_find_container_caches())

    discovered_items = []
    if deep:
        deep_dirs = config.get("deep_scan_dirs", [])

        yield sse({"type": "progress", "phase": "deep", "message": "Finding node_modules..."})
        known_items.extend(_find_node_modules(deep_dirs))

        yield sse({"type": "progress", "phase": "deep", "message": "Finding large .git repos..."})
        known_items.extend(_find_large_git(deep_dirs))

        yield sse({"type": "progress", "phase": "deep", "message": "Finding large log files..."})
        known_items.extend(_find_log_files(deep_dirs))

        yield sse({"type": "progress", "phase": "deep", "message": "Finding large files..."})
        min_bytes = config.get("large_file_min_bytes", 500_000_000)
        extensions = config.get("large_file_extensions", [])
        known_items.extend(_find_large_files(min_bytes, extensions))

        # Space hogs discovery
        yield sse({"type": "progress", "phase": "discover", "message": "Discovering space hogs across ~/..."})

        def progress_cb(phase, current, total, message):
            pass  # Can't yield from callback, but we send updates before/after

        discovered_items = discover_space_hogs(
            min_bytes=100_000_000, top_n=50, progress_callback=None,
        )

        # Remove discovered items that overlap with known items
        known_paths = {item["path"] for item in known_items}
        discovered_items = [
            item for item in discovered_items
            if item["path"] not in known_paths
            and not any(item["path"].startswith(kp + "/") or kp.startswith(item["path"] + "/")
                        for kp in known_paths)
        ]

    # Sort known items by ROI
    weight = {"safe": 1.0, "review": 0.6, "personal": 0.3}
    known_items.sort(key=lambda x: x["size"] * weight.get(x["category"], 0.5), reverse=True)
    discovered_items.sort(key=lambda x: x["size"], reverse=True)

    yield sse({
        "type": "done",
        "known_items": known_items,
        "discovered_items": discovered_items,
        "known_count": len(known_items),
        "discovered_count": len(discovered_items),
    })
