"""Read-only space finders: large files, duplicate files and installed apps.

None of these functions delete or modify anything. Duplicate detection does read
file contents (to hash them) locally; nothing leaves the machine.
"""
from __future__ import annotations

import hashlib
import os
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

from .cleaner import _entry_is_link, _valid_root, _walk_files
from .diagnostics import _powershell_json

MB = 1024 * 1024


def _user_roots() -> list[Path]:
    home = Path.home()
    names = ("Downloads", "Desktop", "Documents", "Videos", "Pictures", "Music")
    return [home / n for n in names if (home / n).is_dir()]


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def find_large_files(min_mb: int = 500, limit: int = 25, extra_path: str | None = None, time_budget: int = 25) -> dict:
    roots = _user_roots()
    if extra_path:
        try:
            p = Path(extra_path).expanduser().resolve(strict=True)
        except (OSError, RuntimeError):
            return {"available": False, "error": "The selected path does not exist or cannot be accessed."}
        if not p.is_dir():
            return {"available": False, "error": "Choose a folder or drive, not an individual file."}
        roots = [p]
    if not roots:
        return {"available": False, "error": "No user folders found to scan."}
    min_bytes = max(1, int(min_mb)) * MB
    deadline = time.monotonic() + time_budget
    found, started = [], time.monotonic()
    for root in roots:
        for path, size, mtime in _walk_files(root, deadline, max_entries=500_000):
            if size >= min_bytes:
                found.append({"path": str(path), "name": path.name, "size_mb": round(size / MB, 1),
                              "size_bytes": size, "modified": _iso(mtime),
                              "days_since_modified": int((time.time() - mtime) / 86400)})
    found.sort(key=lambda x: x["size_bytes"], reverse=True)
    return {"available": True, "roots": [str(r) for r in roots], "min_mb": min_mb, "files": found[:max(1, min(limit, 100))],
            "total_found": len(found), "elapsed_seconds": round(time.monotonic() - started, 1),
            "truncated": time.monotonic() > deadline,
            "note": "Report only. Review each file yourself and delete via File Explorer if you no longer need it. "
                    "'Days since modified' is the last edit date, not the last time you opened it."}


def _hash_file(path: Path, partial: bool) -> str | None:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            if partial:
                h.update(f.read(65536))
                try:
                    f.seek(-65536, os.SEEK_END)
                    h.update(f.read(65536))
                except OSError:
                    pass
            else:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def find_duplicates(path: str, min_mb: int = 1, time_budget: int = 40) -> dict:
    try:
        root = Path(path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        return {"available": False, "error": "The selected path does not exist or cannot be accessed."}
    if not root.is_dir():
        return {"available": False, "error": "Choose a folder or drive, not an individual file."}
    if len(root.parts) < 2:
        return {"available": False, "error": "Choose a specific folder (for example Downloads) rather than a whole drive."}
    min_bytes = max(1, int(min_mb)) * MB
    started = time.monotonic()
    deadline = started + time_budget
    by_size: dict[int, list[Path]] = {}
    for p, size, _m in _walk_files(root, deadline, max_entries=400_000):
        if size >= min_bytes:
            by_size.setdefault(size, []).append(p)
    candidates = {s: ps for s, ps in by_size.items() if len(ps) > 1}
    groups = []
    for size, paths in candidates.items():
        if time.monotonic() > deadline:
            break
        partial: dict[str, list[Path]] = {}
        for p in paths:
            hx = _hash_file(p, partial=True)
            if hx:
                partial.setdefault(hx, []).append(p)
        for same in partial.values():
            if len(same) < 2:
                continue
            full: dict[str, list[Path]] = {}
            for p in same:
                if time.monotonic() > deadline:
                    break
                hx = _hash_file(p, partial=False)
                if hx:
                    full.setdefault(hx, []).append(p)
            for dupes in full.values():
                if len(dupes) > 1:
                    groups.append({"size_mb": round(size / MB, 1), "size_bytes": size, "copies": len(dupes),
                                   "wasted_mb": round(size * (len(dupes) - 1) / MB, 1),
                                   "wasted_bytes": size * (len(dupes) - 1),
                                   "paths": sorted(str(d) for d in dupes)})
    groups.sort(key=lambda g: g["wasted_bytes"], reverse=True)
    return {"available": True, "path": str(root), "groups": groups[:25], "group_count": len(groups),
            "total_wasted_mb": round(sum(g["wasted_bytes"] for g in groups) / MB, 1),
            "elapsed_seconds": round(time.monotonic() - started, 1), "truncated": time.monotonic() > deadline,
            "note": "Byte-for-byte identical files (verified by SHA-256). Report only: keep one copy and delete the others yourself in File Explorer."}


def installed_apps() -> dict:
    if platform.system() != "Windows":
        return {"available": False, "apps": [], "reason": "Installed-app audit supports Windows only."}
    script = r"""
    $paths = @('HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
               'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
               'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*')
    $apps = foreach ($p in $paths) {
      Get-ItemProperty -Path $p -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -and -not $_.SystemComponent -and -not $_.ParentKeyName } |
        Select-Object DisplayName, Publisher, DisplayVersion, InstallDate, EstimatedSize
    }
    @($apps) | ConvertTo-Json -Compress -Depth 3
    """
    res = _powershell_json(script, timeout=25)
    if res is None:
        return {"available": False, "apps": [], "reason": "Installed programs could not be read."}
    if isinstance(res, dict):
        res = [res]
    seen, apps = set(), []
    for a in res:
        name = (a.get("DisplayName") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        kb = a.get("EstimatedSize")
        apps.append({"name": name, "publisher": a.get("Publisher"), "version": a.get("DisplayVersion"),
                     "install_date": a.get("InstallDate"),
                     "size_mb": round(int(kb) / 1024, 1) if isinstance(kb, (int, float)) and kb else None})
    apps.sort(key=lambda x: (x["size_mb"] is None, -(x["size_mb"] or 0), x["name"].lower()))
    return {"available": True, "apps": apps, "count": len(apps),
            "note": "Report only. Sizes are what each installer declares and may be missing. Uninstall via Settings > Apps > Installed apps."}
