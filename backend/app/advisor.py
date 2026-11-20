"""Smart advisor: turns raw telemetry into a short, prioritized, explained to-do list.

It is rule-based and transparent: every recommendation names the evidence it is
based on, and nothing is changed automatically.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import psutil

from . import cleaner, database, diagnostics, startup_manager
from .diagnostics import _powershell_json

GB = 1024 ** 3
MB = 1024 ** 2

# Programs that commonly auto-start but are rarely needed at sign-in.
# Matching is a *lead*, never a verdict - the user decides.
COMMON_OPTIONAL = [
    (r"spotify", "Spotify"), (r"discord", "Discord"), (r"steam", "Steam"), (r"epic ?games", "Epic Games Launcher"),
    (r"teams", "Microsoft Teams"), (r"onedrive", "OneDrive"), (r"skype", "Skype"), (r"zoom", "Zoom"),
    (r"adobe.*(update|creative|acrobat)|acrotray|ccxprocess|adobegc", "Adobe background helpers"),
    (r"itunes|ipod|apple", "Apple helpers"), (r"dropbox", "Dropbox"), (r"google ?drive", "Google Drive"),
    (r"utorrent|bittorrent", "Torrent client"), (r"cortana|yourphone|phone ?link", "Phone Link/Cortana"),
    (r"java ?update|jusched", "Java updater"), (r"ccleaner", "CCleaner"), (r"whatsapp|telegram", "Messaging app"),
]


def _item(id_, priority, severity, title, detail, evidence, view=None, label=None):
    return {"id": id_, "priority": priority, "severity": severity, "title": title, "detail": detail,
            "evidence": evidence, "action": {"view": view, "label": label} if view else None}


def _fmt_bytes(b: int) -> str:
    return f"{b / GB:.1f} GB" if b >= GB else f"{b / MB:.0f} MB"


def _defender_enabled():
    res = _powershell_json(
        "try { Get-MpComputerStatus | Select-Object RealTimeProtectionEnabled, AntivirusEnabled | ConvertTo-Json -Compress } catch {}",
        timeout=15)
    if isinstance(res, list):
        res = res[0] if res else None
    return res


def build_advice() -> dict:
    items: list[dict] = []
    metrics = diagnostics.live_metrics()
    disks = diagnostics.storage_info()
    junk = cleaner.scan(per_category_seconds=4.0)
    startup = startup_manager.list_startup()
    history = database.get_history(limit=6)

    # 1. Reclaimable junk
    if junk.get("available"):
        safe_bytes = sum(c["bytes"] for c in junk["categories"] if c["risk"] == "safe")
        review_bytes = sum(c["bytes"] for c in junk["categories"] if c["risk"] != "safe")
        top = sorted(junk["categories"], key=lambda c: c["bytes"], reverse=True)[:3]
        top_txt = ", ".join(f"{c['label']} ({_fmt_bytes(c['bytes'])})" for c in top if c["bytes"] > 0)
        if safe_bytes >= GB:
            items.append(_item("junk-high", 1, "warning", f"{_fmt_bytes(safe_bytes)} of safe-to-remove junk found",
                               "Temporary files and browser caches are rebuilt automatically, so removing them is low risk.",
                               top_txt, "cleaner", "Review & clean"))
        elif safe_bytes >= 200 * MB:
            items.append(_item("junk-mid", 2, "info", f"{_fmt_bytes(safe_bytes)} of junk can be cleaned",
                               "Not urgent, but an easy win.", top_txt, "cleaner", "Review & clean"))
        if review_bytes >= GB:
            items.append(_item("junk-review", 3, "info", f"{_fmt_bytes(review_bytes)} more to review (Recycle Bin, dumps, dev caches)",
                               "These need your decision because they can't be undone or you may still need them.",
                               "Shown unticked by default in the cleaner.", "cleaner", "Review"))

    # 2. Disk space
    for d in disks:
        if d["free_gb"] < 15 or d["used_percent"] >= 90:
            items.append(_item(f"disk-{d['mountpoint']}", 1, "warning", f"{d['mountpoint']} is nearly full",
                               "Windows needs free space for updates, the page file and temp files. Under ~15 GB free causes slowdowns.",
                               f"{d['free_gb']} GB free ({d['used_percent']}% used)", "space", "Find large files"))
        elif d["used_percent"] >= 80:
            items.append(_item(f"disk-{d['mountpoint']}", 3, "info", f"{d['mountpoint']} is getting full",
                               "Worth finding big files you no longer need before it becomes a problem.",
                               f"{d['free_gb']} GB free ({d['used_percent']}% used)", "space", "Find large files"))

    # 3. Startup load
    if startup.get("available"):
        enabled = [i for i in startup["items"] if i["enabled"]]
        flagged = []
        for i in enabled:
            for pat, label in COMMON_OPTIONAL:
                if re.search(pat, f"{i['name']} {i['command']}", re.I):
                    flagged.append(f"{i['name']} ({label})")
                    break
        if flagged:
            items.append(_item("startup-optional", 2, "info", f"{len(flagged)} startup app(s) usually don't need to launch at sign-in",
                               "Disabling is reversible and makes boot and sign-in faster. You can still open them manually.",
                               ", ".join(flagged[:6]), "startup", "Manage startup"))
        if len(enabled) >= 10:
            items.append(_item("startup-count", 2, "info", f"{len(enabled)} programs start with Windows",
                               "A long startup list slows sign-in and uses memory in the background.",
                               f"{len(enabled)} enabled Run entries", "startup", "Manage startup"))

    # 4. Memory pressure + biggest processes
    if metrics["memory_percent"] >= 85:
        procs = diagnostics.process_analysis(limit=5)["processes"]
        names = ", ".join(f"{p['name']} ({p['memory_mb']:.0f} MB)" for p in procs[:4])
        items.append(_item("memory", 1 if metrics["memory_percent"] >= 92 else 2, "warning", "Memory usage is high",
                           "Closing heavy apps or browser tabs will help. If this is constant, more RAM is the real fix.",
                           f"{metrics['memory_percent']}% used. Biggest: {names}", "diagnostics", "See processes"))

    # 5. Uptime
    try:
        days = (datetime.now(timezone.utc).timestamp() - psutil.boot_time()) / 86400
        if days >= 10:
            items.append(_item("uptime", 3, "info", f"PC hasn't fully restarted in {int(days)} days",
                               "With Fast Startup, 'Shut down' doesn't clear everything. A restart applies updates and frees leaked memory.",
                               f"{int(days)} days since boot"))
    except Exception:
        pass

    # 6. Security
    defender = _defender_enabled()
    if defender and defender.get("RealTimeProtectionEnabled") is False:
        items.append(_item("defender", 1, "critical", "Microsoft Defender real-time protection is off",
                           "Unless another security product is active, turn it on in Windows Security.",
                           "RealTimeProtectionEnabled = False"))

    # 7. Trend from saved scans
    if len(history) >= 3:
        newest, oldest = history[0]["health_score"], history[-1]["health_score"]
        if oldest - newest >= 10:
            items.append(_item("trend", 2, "warning", f"Health score fell from {oldest} to {newest} across recent scans",
                               "Something changed. Compare the findings from your latest scan with an older one.",
                               f"Last {len(history)} scans", "overview", "Run new scan"))

    items.sort(key=lambda x: x["priority"])
    crit = sum(1 for i in items if i["severity"] in ("critical", "warning"))
    if not items:
        summary = "Your PC looks healthy. No cleanup or tuning stands out right now."
    else:
        summary = f"{len(items)} recommendation(s), {crit} worth doing soon. Everything below is optional and nothing is changed until you click."
    return {"available": True, "generated_at": datetime.now(timezone.utc).isoformat(), "summary": summary,
            "recommendations": items,
            "note": "Rule-based analysis of this PC's own data. Recommendations are leads based on the evidence shown, not guarantees."}
