"""Deletion logic — trash or permanent."""

import os
import shutil
import subprocess
from pathlib import Path
from backend.config import log_deletion


def move_to_trash(path: str) -> bool:
    """Move a file/folder to macOS Trash using AppleScript (safe)."""
    p = Path(path)
    if not p.exists():
        return False
    try:
        # Use macOS Finder to move to trash
        script = f'tell application "Finder" to delete POSIX file "{path}"'
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            log_deletion(path, "trash")
            return True
        # Fallback: manual move to ~/.Trash
        trash = Path.home() / ".Trash" / p.name
        if trash.exists():
            # Add suffix to avoid collision
            i = 1
            while trash.exists():
                trash = Path.home() / ".Trash" / f"{p.stem}_{i}{p.suffix}"
                i += 1
        shutil.move(str(p), str(trash))
        log_deletion(path, "trash")
        return True
    except Exception:
        return False


def delete_permanently(path: str) -> bool:
    """Permanently delete a file or folder."""
    p = Path(path)
    if not p.exists():
        return False
    try:
        if p.is_file() or p.is_symlink():
            p.unlink()
        else:
            shutil.rmtree(str(p))
        log_deletion(path, "permanent")
        return True
    except Exception:
        return False


def delete_items(paths: list[str], method: str = "trash") -> dict:
    """Delete multiple items. Returns summary of results."""
    results = {"success": [], "failed": []}
    fn = move_to_trash if method == "trash" else delete_permanently
    for path in paths:
        if fn(path):
            results["success"].append(path)
        else:
            results["failed"].append(path)
    return results
