"""Startup manager: list Run-key entries with their enabled/disabled state and
toggle HKCU entries the same reversible way Task Manager does (StartupApproved).
Nothing is deleted; disabling can always be undone.
"""
from __future__ import annotations

import re

from .diagnostics import _powershell_json


def list_startup() -> dict:
    script = r"""
    $out = @()
    $targets = @(
      @{ scope='User';    run='HKCU:\Software\Microsoft\Windows\CurrentVersion\Run';
         appr='HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run' },
      @{ scope='Machine'; run='HKLM:\Software\Microsoft\Windows\CurrentVersion\Run';
         appr='HKLM:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run' }
    )
    foreach ($t in $targets) {
      if (-not (Test-Path $t.run)) { continue }
      $props = Get-ItemProperty -Path $t.run
      $approved = $null
      if (Test-Path $t.appr) { $approved = Get-ItemProperty -Path $t.appr }
      foreach ($p in $props.PSObject.Properties) {
        if ($p.Name -match '^PS') { continue }
        $enabled = $true
        if ($approved -and $approved.PSObject.Properties[$p.Name]) {
          $b = $approved.($p.Name)
          if ($b -is [byte[]] -and $b.Length -gt 0 -and ($b[0] -band 1) -eq 1) { $enabled = $false }
        }
        $out += [pscustomobject]@{ name=$p.Name; command=[string]$p.Value; scope=$t.scope; enabled=$enabled }
      }
    }
    @($out) | ConvertTo-Json -Compress -Depth 3
    """
    res = _powershell_json(script, timeout=15)
    if res is None:
        return {"available": False, "items": [], "reason": "Startup entries could not be read."}
    if isinstance(res, dict):
        res = [res]
    return {"available": True, "items": res or [],
            "note": "Disabling is reversible and only changes whether Windows launches the entry at sign-in. "
                    "Machine-wide entries need Administrator rights; manage those in Task Manager > Startup apps."}


def set_user_startup(name: str, enabled: bool) -> dict:
    if not name or len(name) > 200 or re.search(r"[\x00-\x1f]", name):
        return {"ok": False, "error": "Invalid startup entry name."}
    script = r"""
    $name = $env:PCDOC_STARTUP_NAME
    $enable = $env:PCDOC_STARTUP_ENABLE -eq '1'
    $run  = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    $appr = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run'
    $props = Get-ItemProperty -Path $run -ErrorAction SilentlyContinue
    if (-not $props -or -not $props.PSObject.Properties[$name]) {
      [pscustomobject]@{ok=$false; error='That entry is not in your user Run key.'} | ConvertTo-Json -Compress; return
    }
    if (-not (Test-Path $appr)) { New-Item -Path $appr -Force | Out-Null }
    if ($enable) { $bytes = [byte[]](2,0,0,0,0,0,0,0,0,0,0,0) }
    else {
      $bytes = [byte[]](3,0,0,0) + [BitConverter]::GetBytes([DateTime]::UtcNow.ToFileTime())
    }
    Set-ItemProperty -Path $appr -Name $name -Value $bytes -Type Binary
    [pscustomobject]@{ok=$true} | ConvertTo-Json -Compress
    """
    res = _powershell_json(script, timeout=15, env={"PCDOC_STARTUP_NAME": name, "PCDOC_STARTUP_ENABLE": "1" if enabled else "0"})
    if not res:
        return {"ok": False, "error": "Windows did not accept the change."}
    return {"ok": bool(res.get("ok")), "error": res.get("error"), "name": name, "enabled": enabled}
