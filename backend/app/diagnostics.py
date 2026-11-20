from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil


def _powershell_json(script: str, timeout: int = 12, env: dict | None = None) -> Any:
    """Run a PowerShell script and parse its JSON output.

    `env` passes extra values to the script via environment variables so that
    user-supplied text is never interpolated into PowerShell source.
    """
    if platform.system() != "Windows":
        return None
    try:
        run_env = {**os.environ, **(env or {})}
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), env=run_env,
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            return None
        return json.loads(completed.stdout.strip())
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return None


def _safe_float(value):
    try:
        return round(float(value), 1) if value is not None else None
    except (TypeError, ValueError):
        return None


def system_info() -> dict:
    script = r"""
    $os = Get-CimInstance Win32_OperatingSystem
    $cs = Get-CimInstance Win32_ComputerSystem
    $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
    [pscustomobject]@{
      caption = $os.Caption
      version = $os.Version
      build = $os.BuildNumber
      manufacturer = $cs.Manufacturer
      model = $cs.Model
      totalMemoryBytes = [int64]$cs.TotalPhysicalMemory
      cpuName = $cpu.Name
      logicalProcessors = $cpu.NumberOfLogicalProcessors
    } | ConvertTo-Json -Compress
    """
    win = _powershell_json(script) or {}
    return {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "windows_caption": win.get("caption"),
        "windows_version": win.get("version"),
        "windows_build": win.get("build"),
        "manufacturer": win.get("manufacturer"),
        "model": win.get("model"),
        "cpu_name": win.get("cpuName") or platform.processor() or "Not reported",
        "logical_processors": win.get("logicalProcessors") or psutil.cpu_count(logical=True),
        "total_memory_gb": round(psutil.virtual_memory().total / (1024**3), 1),
    }


def battery_info() -> dict:
    if not hasattr(psutil, "sensors_battery"):
        return {"available": False, "reason": "Battery telemetry is not supported by this system."}
    try:
        battery = psutil.sensors_battery()
        if battery is None:
            return {"available": False, "reason": "No battery detected (this may be a desktop PC)."}
        return {
            "available": True,
            "percent": round(battery.percent, 1),
            "plugged_in": battery.power_plugged,
            "seconds_left": battery.secsleft if battery.secsleft >= 0 else None,
        }
    except Exception:
        return {"available": False, "reason": "Battery information could not be read."}


def storage_info() -> list[dict]:
    disks = []
    for part in psutil.disk_partitions(all=False):
        if "cdrom" in part.opts.lower():
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "device": part.device,
                "mountpoint": part.mountpoint,
                "filesystem": part.fstype,
                "total_gb": round(usage.total / (1024**3), 1),
                "used_gb": round(usage.used / (1024**3), 1),
                "free_gb": round(usage.free / (1024**3), 1),
                "used_percent": round(usage.percent, 1),
            })
        except (PermissionError, OSError):
            continue
    return disks


def startup_items() -> dict:
    script = r"""
    $items = @()
    $paths = @(
      'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run',
      'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run'
    )
    foreach ($p in $paths) {
      if (Test-Path $p) {
        $props = Get-ItemProperty -Path $p
        foreach ($prop in $props.PSObject.Properties) {
          if ($prop.Name -notmatch '^PS') {
            $items += [pscustomobject]@{ name=$prop.Name; command=[string]$prop.Value; source=$p }
          }
        }
      }
    }
    $items | ConvertTo-Json -Compress -Depth 3
    """
    result = _powershell_json(script)
    if result is None:
        return {"available": False, "items": [], "reason": "Startup registry entries could not be read."}
    if isinstance(result, dict):
        result = [result]
    return {"available": True, "items": result or []}


def physical_disk_health() -> dict:
    script = r"""
    $disks = Get-PhysicalDisk -ErrorAction Stop |
      Select-Object FriendlyName, MediaType, HealthStatus, OperationalStatus, Size
    $disks | ConvertTo-Json -Compress -Depth 3
    """
    result = _powershell_json(script)
    if result is None:
        return {"available": False, "disks": [], "reason": "Windows did not provide physical disk health data."}
    if isinstance(result, dict):
        result = [result]
    parsed = []
    for d in (result or []):
        size = d.get("Size")
        parsed.append({
            "name": d.get("FriendlyName"),
            "media_type": d.get("MediaType"),
            "health_status": d.get("HealthStatus"),
            "operational_status": d.get("OperationalStatus"),
            "size_gb": round(int(size) / (1024**3), 1) if size else None,
        })
    return {"available": True, "disks": parsed}


def temperatures() -> dict:
    # Windows has no universal, reliable built-in CPU/GPU temperature API.
    return {
        "available": False,
        "cpu_celsius": None,
        "gpu_celsius": None,
        "reason": "No supported hardware sensor provider is configured. A future phase can integrate LibreHardwareMonitor.",
    }


def live_metrics() -> dict:
    cpu = psutil.cpu_percent(interval=0.35)
    memory = psutil.virtual_memory()
    boot = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc).isoformat()
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cpu_percent": round(cpu, 1),
        "memory_percent": round(memory.percent, 1),
        "memory_used_gb": round(memory.used / (1024**3), 1),
        "memory_total_gb": round(memory.total / (1024**3), 1),
        "disk_percent": max((d["used_percent"] for d in storage_info()), default=None),
        "boot_time": boot,
        "temperatures": temperatures(),
    }


def _health_score(metrics: dict, disks: list[dict], physical: dict) -> tuple[int, list[dict]]:
    score = 100
    findings = []
    cpu = metrics["cpu_percent"]
    mem = metrics["memory_percent"]
    if cpu >= 95:
        score -= 15
        findings.append({"severity": "warning", "title": "Very high CPU usage", "detail": f"CPU was {cpu}% during the scan. Check Task Manager for sustained heavy processes."})
    elif cpu >= 80:
        score -= 7
        findings.append({"severity": "info", "title": "Elevated CPU usage", "detail": f"CPU was {cpu}% during the scan. A short spike can be normal."})
    if mem >= 95:
        score -= 18
        findings.append({"severity": "warning", "title": "Memory pressure", "detail": f"RAM usage was {mem}%. Close unused apps and inspect high-memory processes."})
    elif mem >= 85:
        score -= 8
        findings.append({"severity": "info", "title": "High memory usage", "detail": f"RAM usage was {mem}%. Check whether this is sustained."})
    for disk in disks:
        if disk["free_gb"] < 10 or disk["used_percent"] >= 95:
            score -= 15
            findings.append({"severity": "warning", "title": f"Low disk space on {disk['mountpoint']}", "detail": f"{disk['free_gb']} GB free ({disk['used_percent']}% used). Free space before large updates or downloads."})
        elif disk["used_percent"] >= 85:
            score -= 5
            findings.append({"severity": "info", "title": f"Disk space getting low on {disk['mountpoint']}", "detail": f"{disk['free_gb']} GB free ({disk['used_percent']}% used)."})
    for d in physical.get("disks", []):
        status = str(d.get("health_status") or "").lower()
        if status and status not in ("healthy", "unknown"):
            score -= 25
            findings.append({"severity": "critical", "title": f"Physical disk reports {d.get('health_status')}", "detail": f"{d.get('name') or 'A physical disk'} reported {d.get('health_status')}. Back up important data and investigate."})
    if not findings:
        findings.append({"severity": "success", "title": "No obvious resource or storage-space issues", "detail": "The quick scan did not find high CPU/RAM usage or critically low disk space. This does not rule out intermittent hardware or software faults."})
    return max(0, min(100, score)), findings


def run_scan() -> dict:
    # A small interval gives CPU usage a meaningful sample instead of an uninitialized reading.
    metrics = live_metrics()
    info = system_info()
    disks = storage_info()
    physical = physical_disk_health()
    startup = startup_items()
    battery = battery_info()
    score, findings = _health_score(metrics, disks, physical)
    return {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "health_score": score,
        "health_label": "Good" if score >= 85 else "Needs attention" if score >= 65 else "At risk",
        "system": info,
        "metrics": metrics,
        "storage": disks,
        "physical_disks": physical,
        "startup": startup,
        "battery": battery,
        "temperatures": temperatures(),
        "findings": findings,
        "scope_note": "This is a baseline scan, not a definitive hardware diagnosis. Use the Smart Advisor tab for prioritized, explained recommendations.",
    }


def process_analysis(limit: int = 20) -> dict:
    """Return a point-in-time, read-only snapshot of resource-heavy processes."""
    rows = []
    for proc in psutil.process_iter(['pid', 'name', 'username', 'memory_info', 'cpu_percent']):
        try:
            info = proc.info
            mem = info.get('memory_info')
            rows.append({
                'pid': info.get('pid'),
                'name': info.get('name') or 'Unknown',
                'username': info.get('username'),
                'memory_mb': round(mem.rss / (1024 ** 2), 1) if mem else 0,
                'cpu_percent': round(float(info.get('cpu_percent') or 0), 1),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    rows.sort(key=lambda x: (x['memory_mb'], x['cpu_percent']), reverse=True)
    return {'available': True, 'sample_note': 'Point-in-time process snapshot. CPU percentages may need a second sample to become meaningful.', 'processes': rows[:max(1, min(limit, 50))]}


def storage_analysis(target: str, max_depth: int = 2, max_entries: int = 12000, time_budget: int = 10) -> dict:
    """Bounded folder-size walk. Reads metadata only; never opens file contents or deletes files."""
    if platform.system() != 'Windows':
        return {'available': False, 'error': 'Storage folder analysis is currently supported on Windows only.'}
    try:
        root = Path(target).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        return {'available': False, 'error': 'The selected path does not exist or cannot be accessed.'}
    if not root.is_dir():
        return {'available': False, 'error': 'Choose a folder or drive, not an individual file.'}

    started = time.monotonic()
    visited = 0
    total_bytes = 0
    folders = []
    stack = [(root, 0)]
    truncated = False
    while stack:
        if visited >= max_entries or time.monotonic() - started > time_budget:
            truncated = True
            break
        current, depth = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if visited >= max_entries or time.monotonic() - started > time_budget:
                        truncated = True
                        break
                    visited += 1
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False) and depth < max_depth:
                            stack.append((Path(entry.path), depth + 1))
                        elif entry.is_file(follow_symlinks=False):
                            total_bytes += entry.stat(follow_symlinks=False).st_size
                    except (PermissionError, OSError):
                        continue
            if depth < max_depth:
                # Size summaries are gathered for immediate child folders in a separate bounded walk below.
                pass
        except (PermissionError, OSError):
            continue

    # A lightweight first-level breakdown. Each child is walked with the same global limits.
    try:
        children = list(os.scandir(root))
    except (PermissionError, OSError):
        children = []
    for child in children:
        if not child.is_dir(follow_symlinks=False) or child.is_symlink():
            continue
        size = 0
        pending = [Path(child.path)]
        local_count = 0
        while pending and local_count < 2500 and time.monotonic() - started < time_budget:
            folder = pending.pop()
            try:
                with os.scandir(folder) as entries:
                    for item in entries:
                        local_count += 1
                        if local_count >= 2500:
                            truncated = True
                            break
                        try:
                            if item.is_symlink():
                                continue
                            if item.is_dir(follow_symlinks=False):
                                pending.append(Path(item.path))
                            elif item.is_file(follow_symlinks=False):
                                size += item.stat(follow_symlinks=False).st_size
                        except (PermissionError, OSError):
                            continue
            except (PermissionError, OSError):
                continue
        folders.append({'name': child.name, 'path': child.path, 'size_gb': round(size / (1024 ** 3), 3), 'size_bytes': size})
    folders.sort(key=lambda x: x['size_bytes'], reverse=True)
    return {
        'available': True, 'path': str(root), 'folders': folders[:30],
        'entries_visited': visited, 'elapsed_seconds': round(time.monotonic() - started, 2),
        'truncated': truncated or time.monotonic() - started >= time_budget,
        'safety_note': 'Metadata-only scan. File contents were not opened, and nothing was changed or deleted.'
    }


def windows_health() -> dict:
    """Read-only Windows health signals; unavailable checks are reported honestly."""
    script = r"""
    $disk = @()
    try { $disk = @(Get-PhysicalDisk | Select-Object FriendlyName, HealthStatus, OperationalStatus) } catch {}
    $events = @()
    try {
      $events = @(Get-WinEvent -FilterHashtable @{LogName='System'; Level=1,2; StartTime=(Get-Date).AddDays(-7)} -MaxEvents 15 -ErrorAction Stop |
        Select-Object TimeCreated, Id, ProviderName, LevelDisplayName, Message)
    } catch {}
    $defender = $null
    try { $defender = Get-MpComputerStatus | Select-Object AntivirusEnabled, RealTimeProtectionEnabled, AntivirusSignatureLastUpdated } catch {}
    [pscustomobject]@{ physicalDisks=$disk; criticalEvents=$events; defender=$defender } | ConvertTo-Json -Compress -Depth 5
    """
    result = _powershell_json(script, timeout=20)
    if result is None:
        return {'available': False, 'physical_disks': [], 'critical_events': [], 'defender': None,
                'reason': 'Windows health checks could not be read. Some checks may require Windows PowerShell permissions or Defender availability.'}
    disks = result.get('physicalDisks') or []
    events = result.get('criticalEvents') or []
    if isinstance(disks, dict): disks = [disks]
    if isinstance(events, dict): events = [events]
    defender = result.get('defender')
    if isinstance(defender, list): defender = defender[0] if defender else None
    return {'available': True, 'physical_disks': disks, 'critical_events': events, 'defender': defender,
            'window_days': 7, 'note': 'Event log entries are signals for investigation, not proof of a hardware fault.'}



def system_stability_analysis(days: int = 7) -> dict:
    """Read-only stability review of selected Windows System/Application events."""
    days = max(1, min(int(days), 30))
    script = rf"""
    $since = (Get-Date).AddDays(-{days})
    $wantedIds = @(41, 6008, 1001, 7, 11, 15, 51, 55, 98, 129, 153, 157, 7000, 7001, 7009, 7011, 7023, 7024, 7031, 7034, 7043, 10010, 10016, 2042)
    $providers = @('Microsoft-Windows-Windows Firewall With Advanced Security', 'Microsoft-Windows-DistributedCOM', 'Microsoft-Windows-Kernel-Power', 'Microsoft-Windows-Kernel-General', 'Microsoft-Windows-WER-SystemErrorReporting', 'Disk', 'Ntfs', 'storahci', 'stornvme', 'iaStorAC', 'Service Control Manager', 'EventLog', 'volmgr')
    $events = @()
    foreach ($log in @('System','Application')) {{
      try {{
        $events += @(Get-WinEvent -FilterHashtable @{{LogName=$log; StartTime=$since}} -MaxEvents 500 -ErrorAction Stop |
          Where-Object {{ ($wantedIds -contains $_.Id) -or ($providers -contains $_.ProviderName) }} |
          Select-Object -First 250)
      }} catch {{}}
    }}
    $events = @($events | Sort-Object TimeCreated -Descending | Select-Object -First 250)
    $output = @($events | ForEach-Object {{
      $iso = $null
      if ($_.TimeCreated) {{ $iso = $_.TimeCreated.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ', [Globalization.CultureInfo]::InvariantCulture) }}
      [pscustomobject]@{{ time=$iso; id=$_.Id; provider=$_.ProviderName; level=$_.LevelDisplayName; log=$_.LogName; message=[string]$_.Message }}
    }})
    [pscustomobject]@{{ events=$output; days={days}; collectedAt=[DateTime]::UtcNow.ToString('o') }} | ConvertTo-Json -Compress -Depth 5
    """
    result = _powershell_json(script, timeout=35)
    if result is None:
        return {
            'available': False, 'days': days, 'events': [], 'findings': [], 'correlations': [],
            'reason': 'Windows event logs could not be queried. Try running the app with an account allowed to read Event Viewer logs.'
        }

    events = result.get('events') or []
    if isinstance(events, dict):
        events = [events]

    rules = {
        41: ('critical', 'Unexpected shutdown detected', 'Windows recorded that the previous shutdown was not clean. This can follow power loss, a forced power-off, a system hang or a crash; Event 41 alone does not identify the cause.', 'Compare nearby BugCheck, WHEA, disk and EventLog entries. Check whether a dump file exists before considering hardware changes.'),
        6008: ('warning', 'Unexpected shutdown reported', 'The Event Log service recorded an unexpected shutdown. This often accompanies Kernel-Power 41 and is not independent proof of a hardware fault.', 'Compare its timestamp with Kernel-Power 41 and any crash or storage events around the same time.'),
        1001: ('warning', 'Windows bugcheck / error report', 'A Windows error-reporting event may indicate a bugcheck or crash report. The message contains the available details.', 'Read the event message and inspect any referenced minidump before drawing conclusions.'),
        7: ('warning', 'Disk device error', 'The storage stack reported a device-level error. The message and device context are needed to determine significance.', 'Check for repeated events, device name, connection and vendor diagnostics; back up important data if errors recur.'),
        11: ('warning', 'Storage controller error', 'A storage controller reported an error. This can be transient or related to a controller, driver, connection or device.', 'Correlate with Disk, Ntfs and storage-controller events at the same time.'),
        51: ('warning', 'I/O operation warning', 'Windows reported an I/O error while accessing a device.', 'Check whether the event repeats and whether it names a disk or volume.'),
        55: ('warning', 'File-system warning', 'NTFS reported a file-system issue. This event does not by itself establish the extent of any corruption.', 'Back up important files and use Windows-supported file-system checks only after reviewing the volume and event details.'),
        98: ('warning', 'Volume integrity event', 'Windows reported a volume integrity or file-system condition.', 'Review the full message and volume identifier; do not run repair commands automatically.'),
        129: ('warning', 'Storage device reset', 'A storage controller reset a device or timed out waiting for it.', 'Look for repeated resets and nearby disk/controller errors; check firmware and driver information.'),
        153: ('warning', 'Storage I/O retry', 'Windows retried an I/O operation to a storage device.', 'Check for repeated retries and correlate with controller or disk events.'),
        157: ('info', 'Disk surprise removal', 'Windows detected that a disk was unexpectedly removed. This can be expected for removable storage but should be checked for internal drives.', 'Confirm which device was removed and whether it was an external USB drive.'),
        10010: ('info', 'DistributedCOM activation timeout', 'A COM server did not register with DCOM within the expected timeout. This can be application-specific and is not automatically a system failure.', 'Use the event message to identify the CLSID/APPID and affected application; investigate only if users notice related symptoms.'),
        10016: ('info', 'DistributedCOM permission event', 'A DCOM permission event was logged. Many such events are benign and should not be “fixed” by broad registry or permission changes.', 'Check whether a related application or Windows feature is malfunctioning before taking action.'),
        2042: ('warning', 'Windows Firewall event', 'Windows Firewall logged an error. The event message is required to determine whether this affected firewall policy or connectivity.', 'Review the full message and nearby firewall events; verify firewall status in Windows Security.'),
        7000: ('warning', 'Service failed to start', 'The Service Control Manager reported that a service failed to start.', 'Identify the service and error code in the event message; check whether the service is required.'),
        7001: ('warning', 'Service dependency failure', 'A service could not start because a dependency failed.', 'Review both service names and inspect the earlier dependency error.'),
        7009: ('warning', 'Service start timeout', 'A service did not respond within its configured start timeout.', 'Check whether the service is repeatedly timing out and whether a related app is affected.'),
        7011: ('warning', 'Service response timeout', 'A service operation timed out while waiting for a response.', 'Correlate repeated events with application or service symptoms.'),
        7023: ('warning', 'Service terminated with an error', 'A service terminated and reported an error.', 'Read the service name and error code in the event message.'),
        7024: ('warning', 'Service-specific error', 'A service stopped with a service-specific error.', 'Review the service name and error code; avoid changing startup settings without context.'),
        7031: ('warning', 'Service terminated unexpectedly', 'A service terminated unexpectedly. Windows may have attempted recovery.', 'Check whether the same service repeatedly crashes and whether dependent features are affected.'),
        7034: ('warning', 'Service terminated unexpectedly', 'A service terminated unexpectedly without a clean stop.', 'Check recurrence and the service name in the event message.'),
        7043: ('warning', 'Service did not shut down cleanly', 'A service did not shut down as expected after receiving a preshutdown control.', 'Check for recurrence and whether shutdown is delayed.')
    }

    findings = []
    for ev in events:
        try:
            event_id = int(ev.get('id'))
        except (TypeError, ValueError):
            continue
        if event_id not in rules:
            continue
        severity, title, explanation, next_step = rules[event_id]
        findings.append({
            'severity': severity, 'title': title, 'event_id': event_id,
            'provider': ev.get('provider'), 'time': ev.get('time'),
            'log': ev.get('log'), 'explanation': explanation,
            'evidence': (ev.get('message') or '')[:4000],
            'recommended_next_step': next_step
        })

    # Correlate events close in time, without claiming causation.
    parsed = []
    for ev in events:
        try:
            stamp = datetime.fromisoformat(str(ev.get('time')).replace('Z', '+00:00'))
            parsed.append((stamp, ev))
        except (TypeError, ValueError):
            continue
    correlations = []
    anchors = [(t, e) for t, e in parsed if int(e.get('id') or 0) in (41, 6008, 1001)]
    for anchor_time, anchor in anchors[:10]:
        nearby = []
        for stamp, ev in parsed:
            if ev is anchor:
                continue
            delta = abs((stamp - anchor_time).total_seconds())
            if delta <= 600:
                nearby.append({'time': ev.get('time'), 'id': ev.get('id'), 'provider': ev.get('provider'), 'level': ev.get('level'), 'message': (ev.get('message') or '')[:1000]})
        if nearby:
            correlations.append({
                'anchor': {'time': anchor.get('time'), 'id': anchor.get('id'), 'provider': anchor.get('provider')},
                'window_minutes': 10, 'nearby_events': nearby[:20],
                'interpretation': 'These events occurred within 10 minutes of the anchor event. Timing suggests a possible relationship, but does not prove causation.'
            })

    return {
        'available': True, 'days': days, 'collected_at': result.get('collectedAt'),
        'total_events_scanned': len(events), 'events': events,
        'findings': findings, 'correlations': correlations,
        'safety_note': 'Read-only analysis. No services, registry values, firewall rules, files or system settings were changed. Recommendations are investigative steps, not automatic repairs.'
    }


def hardware_inventory() -> dict:
    """Read-only hardware inventory and Plug-and-Play problem summary."""
    script = r"""
    $cpu = @(Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed)
    $memory = @(Get-CimInstance Win32_PhysicalMemory | Select-Object BankLabel, Capacity, Speed, Manufacturer, PartNumber)
    $video = @(Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion, DriverDate, AdapterRAM)
    $bios = Get-CimInstance Win32_BIOS | Select-Object Manufacturer, SMBIOSBIOSVersion, ReleaseDate
    $board = Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer, Product
    $problems = @(Get-CimInstance Win32_PnPEntity | Where-Object { $_.ConfigManagerErrorCode -and $_.ConfigManagerErrorCode -ne 0 } |
      Select-Object Name, PNPClass, DeviceID, ConfigManagerErrorCode, Status)
    [pscustomobject]@{ cpu=$cpu; memory=$memory; video=$video; bios=$bios; board=$board; deviceProblems=$problems } | ConvertTo-Json -Compress -Depth 5
    """
    result = _powershell_json(script, timeout=20)
    if result is None:
        return {"available": False, "reason": "Hardware inventory could not be queried through Windows CIM."}
    def as_list(value):
        if value is None: return []
        return value if isinstance(value, list) else [value]
    return {
        "available": True,
        "cpu": as_list(result.get("cpu")),
        "memory_modules": as_list(result.get("memory")),
        "video_controllers": as_list(result.get("video")),
        "bios": result.get("bios"),
        "baseboard": result.get("board"),
        "device_problems": as_list(result.get("deviceProblems")),
        "note": "A device problem code is a Windows Plug-and-Play status, not a diagnosis. Empty results mean no non-zero ConfigManagerErrorCode was returned.",
    }


def power_diagnostics() -> dict:
    """Read-only power and battery data; does not generate reports or change power settings."""
    script = r"""
    $battery = @()
    try { $battery = @(Get-CimInstance Win32_Battery | Select-Object Name, BatteryStatus, EstimatedChargeRemaining, DesignVoltage, Status) } catch {}
    $static = @()
    try { $static = @(Get-CimInstance -Namespace root\wmi -ClassName BatteryStaticData -ErrorAction Stop | Select-Object InstanceName, DesignedCapacity, DesignedVoltage) } catch {}
    $full = @()
    try { $full = @(Get-CimInstance -Namespace root\wmi -ClassName BatteryFullChargedCapacity -ErrorAction Stop | Select-Object InstanceName, FullChargedCapacity) } catch {}
    $status = @()
    try { $status = @(Get-CimInstance -Namespace root\wmi -ClassName BatteryStatus -ErrorAction Stop | Select-Object InstanceName, PowerOnline, Charging, Discharging, RemainingCapacity, Voltage) } catch {}
    $adapter = @()
    try { $adapter = @(Get-CimInstance Win32_PortableBattery -ErrorAction Stop | Select-Object Name, Status, DesignCapacity, FullChargeCapacity) } catch {}
    $plan = $null
    try { $plan = (powercfg /getactivescheme 2>&1 | Out-String).Trim() } catch {}
    [pscustomobject]@{ battery=$battery; static=$static; full=$full; status=$status; portable=$adapter; activePowerPlan=$plan } | ConvertTo-Json -Compress -Depth 5
    """
    result = _powershell_json(script, timeout=20)
    if result is None:
        return {"available": False, "reason": "Power and battery telemetry could not be queried."}
    def as_list(value):
        if value is None: return []
        return value if isinstance(value, list) else [value]
    return {
        "available": True,
        "battery": as_list(result.get("battery")),
        "battery_static": as_list(result.get("static")),
        "battery_full_charge": as_list(result.get("full")),
        "battery_status": as_list(result.get("status")),
        "portable_battery": as_list(result.get("portable")),
        "active_power_plan": result.get("activePowerPlan"),
        "note": "Battery capacity fields vary by OEM and firmware. Missing values are unavailable, not zero. This check does not test AC-adapter wattage or electrical stability.",
    }


def driver_inventory() -> dict:
    """Read-only signed driver inventory for display and export."""
    script = r"""
    $drivers = @()
    try {
      $drivers = @(Get-CimInstance Win32_PnPSignedDriver -ErrorAction Stop |
        Select-Object DeviceName, DeviceClass, Manufacturer, DriverProviderName, DriverVersion, DriverDate, IsSigned, InfName)
    } catch {}
    [pscustomobject]@{ drivers=$drivers } | ConvertTo-Json -Compress -Depth 4
    """
    result = _powershell_json(script, timeout=25)
    if result is None:
        return {"available": False, "drivers": [], "reason": "Signed driver inventory could not be read."}
    drivers = result.get("drivers") or []
    if isinstance(drivers, dict): drivers = [drivers]
    return {
        "available": True,
        "drivers": drivers,
        "count": len(drivers),
        "note": "This is an inventory only. The app does not decide that a driver is outdated based solely on its version string and does not install or remove drivers.",
    }
