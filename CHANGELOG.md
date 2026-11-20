# Changelog

## 3.1.0
- **Smart Advisor**: rule-based analysis of junk, disk space, startup load, memory, Defender status and scan-score trend, producing a prioritized list with the evidence behind each item.
- **Safe Cleaner**: scan-then-confirm removal of temp files, thumbnail cache, Chrome/Edge/Firefox cache, crash dumps, pip/npm caches and the Recycle Bin. Whitelisted locations only, recent files skipped, links never followed, history logged locally.
- **Space Finder**: large-file finder, SHA-256 duplicate finder and installed-apps-by-size list (report only).
- **Startup Manager**: reversible enable/disable of your user startup entries (same mechanism as Task Manager).
- Sidebar navigation now works (Overview, Advisor, Cleaner, Space Finder, Startup, Diagnostics).
- Fixed: Hardware / Power / Driver panels crashed because their React state was never declared.
- Fixed: storage analyzer default path no longer has a stray escaped backslash.

## 3.0.0
- Preserved Phase 2.1 baseline scan, storage analyzer, process snapshot, startup inventory, Windows health and stability analyzer.
- Added read-only hardware inventory (CPU, RAM, display adapters, BIOS/baseboard and Plug-and-Play problem codes).
- Added read-only battery/power telemetry and active power-plan reporting.
- Added signed driver inventory without automatic update claims or driver changes.
- Expanded README with API list, privacy boundaries and hardware-safety guidance.
- Excluded virtual environments, node_modules, caches and local SQLite databases from the distribution archive.
