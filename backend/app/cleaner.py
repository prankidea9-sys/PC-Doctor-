"""Safe junk cleaner.

Design rules (enforced in code, not just documented):
  * Only categories from the fixed CATEGORIES whitelist can be cleaned; the API
    never accepts a path from the client.
  * Every root must be an absolute path at least 3 components deep (never a drive
    root or C:\\Windows itself) and must exist.
  * Symlinks / junctions / reparse points are never followed or deleted.
  * Files younger than `min_age_hours` are skipped (they may be in use).
  * Locked / in-use files are skipped silently and reported as "skipped".
  * Scan (preview) and clean are separate steps; nothing is deleted by scanning.
"""
from __future__ import annotations

import glob
import os
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPARSE_FLAG = 0x400


def _is_windows() -> bool:
    return platform.system() == "Windows"


def _env(name: str) -> str:
    return os.environ.get(name) or ""


def _valid_root(p: Path | None) -> bool:
    try:
        return bool(p) and p.is_absolute() and len(p.resolve().parts) >= 3 and p.is_dir()
    except OSError:
        return False


def _expand(base: str, *patterns: str) -> list[Path]:
    """Expand glob patterns under `base`. Returns [] if base is unset."""
    if not base:
        return []
    out: list[Path] = []
    for pat in patterns:
        for hit in glob.glob(os.path.join(base, pat)):
            out.append(Path(hit))
    return out


def _cat_defs() -> list[dict]:
    local, temp = _env("LOCALAPPDATA"), _env("TEMP")
    windir, progdata = _env("WINDIR"), _env("PROGRAMDATA")
    chromium_cache = ("*/Cache/Cache_Data", "*/Code Cache", "*/GPUCache")
    return [
        {"id": "user_temp", "label": "User temporary files", "risk": "safe", "default": True,
         "description": "Leftover files in your personal Temp folder.",
         "roots": [Path(temp)] if temp else [], "min_age_hours": 24},
        {"id": "windows_temp", "label": "Windows temporary files", "risk": "safe", "default": True,
         "description": "System-wide Temp folder. Some files need Administrator rights and will be skipped without it.",
         "roots": [Path(windir) / "Temp"] if windir else [], "min_age_hours": 24},
        {"id": "thumbnails", "label": "Thumbnail cache", "risk": "safe", "default": True,
         "description": "Explorer rebuilds these image previews automatically.",
         "roots": _expand(local, r"Microsoft\Windows\Explorer"), "file_glob": "thumbcache_*.db", "min_age_hours": 0},
        {"id": "crash_dumps", "label": "Crash dumps & error reports", "risk": "review", "default": False,
         "description": "Old crash dumps and Windows Error Reporting archives. Keep these if you are still investigating a crash.",
         "roots": _expand(local, "CrashDumps", r"Microsoft\Windows\WER\ReportArchive", r"Microsoft\Windows\WER\ReportQueue")
                  + ([Path(windir) / "Minidump"] if windir else [])
                  + _expand(progdata, r"Microsoft\Windows\WER\ReportArchive"),
         "min_age_hours": 24},
        {"id": "chrome_cache", "label": "Google Chrome cache", "risk": "safe", "default": True,
         "description": "Cached web files only. Passwords, history, cookies and bookmarks are NOT touched. Close Chrome first for best results.",
         "roots": _expand(local, *[os.path.join("Google", "Chrome", "User Data", c) for c in chromium_cache]),
         "min_age_hours": 1},
        {"id": "edge_cache", "label": "Microsoft Edge cache", "risk": "safe", "default": True,
         "description": "Cached web files only. Passwords, history, cookies and bookmarks are NOT touched. Close Edge first for best results.",
         "roots": _expand(local, *[os.path.join("Microsoft", "Edge", "User Data", c) for c in chromium_cache]),
         "min_age_hours": 1},
        {"id": "firefox_cache", "label": "Firefox cache", "risk": "safe", "default": True,
         "description": "Cached web files only. Close Firefox first for best results.",
         "roots": _expand(local, os.path.join("Mozilla", "Firefox", "Profiles", "*", "cache2")), "min_age_hours": 1},
        {"id": "dev_caches", "label": "Developer package caches (pip, npm)", "risk": "review", "default": False,
         "description": "Downloaded package archives. Safe to remove but tools will re-download them when needed.",
         "roots": _expand(local, os.path.join("pip", "Cache"), "npm-cache", os.path.join("npm-cache", "_cacache")),
         "min_age_hours": 24},
        {"id": "recycle_bin", "label": "Recycle Bin", "risk": "review", "default": False,
         "description": "Permanently empties the Recycle Bin. Items cannot be restored afterwards.",
         "roots": [], "special": "recycle_bin", "min_age_hours": 0},
    ]


def _entry_is_link(entry: os.DirEntry) -> bool:
    try:
        if entry.is_symlink():
            return True
        junction = getattr(entry, "is_junction", None)
        if junction and junction():
            return True
        attrs = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
        return bool(attrs & REPARSE_FLAG)
    except OSError:
        return True  # when in doubt, leave it alone


def _walk_files(root: Path, deadline: float, max_entries: int = 300_000):
    """Yield (path, size, mtime) for regular files under root; never follows links."""
    stack, seen = [root], 0
    while stack:
        if time.monotonic() > deadline:
            return
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for entry in it:
                    seen += 1
                    if seen > max_entries or time.monotonic() > deadline:
                        return
                    if _entry_is_link(entry):
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            st = entry.stat(follow_symlinks=False)
                            yield Path(entry.path), st.st_size, st.st_mtime
                    except OSError:
                        continue
        except OSError:
            continue


def _category_files(cat: dict, deadline: float):
    """Yield (root, path, size, mtime) of files that belong to the category."""
    file_glob = cat.get("file_glob")
    for root in cat["roots"]:
        if not _valid_root(root):
            continue
        for path, size, mtime in _walk_files(root, deadline):
            if file_glob and not path.match(file_glob):
                continue
            yield root, path, size, mtime


def _recycle_bin_size() -> dict:
    from .diagnostics import _powershell_json
    script = r"""
    $bytes = 0; $count = 0
    try { $items = (New-Object -ComObject Shell.Application).NameSpace(10).Items()
          foreach ($i in $items) { $count++; $bytes += [int64]$i.Size } } catch {}
    [pscustomobject]@{ bytes=$bytes; count=$count } | ConvertTo-Json -Compress
    """
    res = _powershell_json(script, timeout=20) or {}
    return {"bytes": int(res.get("bytes") or 0), "files": int(res.get("count") or 0)}


def scan(per_category_seconds: float = 8.0) -> dict:
    """Preview what could be cleaned. Deletes nothing."""
    if not _is_windows():
        return {"available": False, "categories": [], "reason": "The cleaner only supports Windows."}
    cats, total = [], 0
    for cat in _cat_defs():
        info: dict[str, Any] = {k: cat[k] for k in ("id", "label", "description", "risk", "default")}
        if cat.get("special") == "recycle_bin":
            rb = _recycle_bin_size()
            info.update(bytes=rb["bytes"], files=rb["files"], skipped_recent=0, present=rb["files"] > 0)
        else:
            deadline = time.monotonic() + per_category_seconds
            cutoff = time.time() - cat["min_age_hours"] * 3600
            size = count = recent = 0
            for _root, _path, sz, mtime in _category_files(cat, deadline):
                if mtime <= cutoff:
                    size += sz
                    count += 1
                else:
                    recent += 1
            info.update(bytes=size, files=count, skipped_recent=recent,
                        present=any(_valid_root(r) for r in cat["roots"]),
                        partial=time.monotonic() > deadline)
        total += info["bytes"]
        cats.append(info)
    return {"available": True, "categories": cats, "total_bytes": total,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "note": "Preview only. Nothing was deleted. Files modified recently are excluded because they may be in use."}


def _clean_recycle_bin() -> dict:
    from .diagnostics import _powershell_json
    before = _recycle_bin_size()
    script = r"""
    try { Clear-RecycleBin -Force -ErrorAction Stop; [pscustomobject]@{ok=$true} | ConvertTo-Json -Compress }
    catch { [pscustomobject]@{ok=$false; error=$_.Exception.Message} | ConvertTo-Json -Compress }
    """
    res = _powershell_json(script, timeout=60) or {}
    ok = bool(res.get("ok"))
    return {"freed_bytes": before["bytes"] if ok else 0, "deleted": before["files"] if ok else 0,
            "skipped": 0 if ok else before["files"], "error": None if ok else (res.get("error") or "Recycle Bin could not be emptied.")}


def _safe_unlink(path: Path, root: Path) -> bool:
    """Delete one file only if it is genuinely inside root. Returns True on success."""
    try:
        resolved = path.resolve()
        root_resolved = root.resolve()
        if os.path.commonpath([str(resolved), str(root_resolved)]) != str(root_resolved):
            return False
        if path.is_symlink():
            return False
        path.unlink()
        return True
    except OSError:
        return False


def _prune_empty_dirs(root: Path, deadline: float) -> None:
    for dirpath, _dirs, _files in os.walk(root, topdown=False, followlinks=False):
        if time.monotonic() > deadline:
            return
        p = Path(dirpath)
        if p == root:
            continue
        try:
            if not os.path.islink(p):
                p.rmdir()  # only succeeds when empty
        except OSError:
            pass


def clean(category_ids: list[str]) -> dict:
    """Delete files in the selected whitelisted categories. Unknown ids are rejected."""
    if not _is_windows():
        return {"available": False, "reason": "The cleaner only supports Windows."}
    defs = {c["id"]: c for c in _cat_defs()}
    unknown = [c for c in category_ids if c not in defs]
    if unknown:
        return {"available": False, "reason": f"Unknown categories: {', '.join(unknown)}"}
    results, freed_total = [], 0
    for cid in dict.fromkeys(category_ids):  # de-duplicate, keep order
        cat = defs[cid]
        if cat.get("special") == "recycle_bin":
            r = _clean_recycle_bin()
        else:
            deadline = time.monotonic() + 60
            cutoff = time.time() - cat["min_age_hours"] * 3600
            freed = deleted = skipped = 0
            for root, path, size, mtime in list(_category_files(cat, deadline)):
                if mtime > cutoff:
                    skipped += 1
                    continue
                if _safe_unlink(path, root):
                    freed += size
                    deleted += 1
                else:
                    skipped += 1
            for root in cat["roots"]:
                if _valid_root(root):
                    _prune_empty_dirs(root, deadline)
            r = {"freed_bytes": freed, "deleted": deleted, "skipped": skipped, "error": None}
        freed_total += r["freed_bytes"]
        results.append({"id": cid, "label": cat["label"], **r})
    return {"available": True, "results": results, "freed_bytes": freed_total,
            "cleaned_at": datetime.now(timezone.utc).isoformat(),
            "note": "Files that were in use or protected were skipped automatically."}
