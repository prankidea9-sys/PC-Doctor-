from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware

from . import advisor, cleaner, database, diagnostics, spacefinder, startup_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    yield


app = FastAPI(title="PC Doctor AI Diagnostic Service", version="3.1.0", lifespan=lifespan)

# Local development UI only. API binds to 127.0.0.1 in the launch instructions.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "PC Doctor AI", "phase": 3.1, "mode": "diagnostics + confirmed actions"}


@app.get("/api/overview")
def overview():
    return {"system": diagnostics.system_info(), "metrics": diagnostics.live_metrics(),
            "storage": diagnostics.storage_info(), "battery": diagnostics.battery_info(),
            "temperatures": diagnostics.temperatures()}


@app.post("/api/scan")
def scan():
    report = diagnostics.run_scan()
    report["scan_id"] = database.save_scan(report)
    return report


@app.get("/api/history")
def history():
    return {"scans": database.get_history()}


@app.get("/api/diagnostics/processes")
def processes():
    return diagnostics.process_analysis()


@app.get("/api/diagnostics/storage")
def storage(path: str = Query(..., min_length=2, max_length=260)):
    return diagnostics.storage_analysis(path)


@app.get("/api/diagnostics/startup")
def startup():
    return diagnostics.startup_items()


@app.get("/api/diagnostics/windows")
def windows():
    return diagnostics.windows_health()


@app.get("/api/diagnostics/stability")
def stability(days: int = Query(7, ge=1, le=30)):
    return diagnostics.system_stability_analysis(days=days)


@app.get("/api/diagnostics/hardware")
def hardware():
    return diagnostics.hardware_inventory()


@app.get("/api/diagnostics/power")
def power():
    return diagnostics.power_diagnostics()


@app.get("/api/diagnostics/drivers")
def drivers():
    return diagnostics.driver_inventory()


# ---- Phase 3.1: advisor, cleaner, space finders, startup manager ----

class CleanRequest(BaseModel):
    categories: list[str] = Field(..., min_length=1, max_length=20)
    confirm: bool = False


class StartupToggle(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    enabled: bool


@app.get("/api/advisor")
def advisor_report():
    return advisor.build_advice()


@app.get("/api/cleaner/scan")
def cleaner_scan():
    return cleaner.scan()


@app.post("/api/cleaner/clean")
def cleaner_clean(req: CleanRequest):
    if not req.confirm:
        raise HTTPException(status_code=400, detail="Cleaning requires explicit confirmation.")
    report = cleaner.clean(req.categories)
    if not report.get("available"):
        raise HTTPException(status_code=400, detail=report.get("reason", "Cleaning is unavailable."))
    report["cleanup_id"] = database.save_cleanup(report)
    return report


@app.get("/api/cleaner/history")
def cleaner_history():
    return {"cleanups": database.get_cleanups()}


@app.get("/api/space/large-files")
def large_files(min_mb: int = Query(500, ge=10, le=100000), path: str | None = Query(None, max_length=260)):
    return spacefinder.find_large_files(min_mb=min_mb, extra_path=path)


@app.get("/api/space/duplicates")
def duplicates(path: str = Query(..., min_length=2, max_length=260), min_mb: int = Query(1, ge=1, le=10000)):
    return spacefinder.find_duplicates(path, min_mb=min_mb)


@app.get("/api/apps")
def apps():
    return spacefinder.installed_apps()


@app.get("/api/startup")
def startup_list():
    return startup_manager.list_startup()


@app.post("/api/startup/toggle")
def startup_toggle(req: StartupToggle):
    result = startup_manager.set_user_startup(req.name, req.enabled)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Could not change startup entry.")
    return result
