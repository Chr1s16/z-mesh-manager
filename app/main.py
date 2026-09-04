import asyncio, os, time, uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .core import APP_ROOT, DATA, host, init_storage, log, save_settings, settings
from .models import ActivateRequest, ActionRequest, SettingsRequest

async def watchdog():
    while True:
        await asyncio.sleep(300)
        cfg = settings()
        if cfg.get("auto_repair"):
            try:
                report = await host("audit")
                provider = report.get("active_provider")
                if provider and not report.get(provider, {}).get("healthy"): await host("repair", provider)
                stamp = DATA / "state" / "last-update-check"
                due = not stamp.exists() or time.time() - stamp.stat().st_mtime >= cfg.get("update_check_hours", 24) * 3600
                if due:
                    stamp.touch()
                    if cfg.get("automatic_updates") and provider in ("tailscale", "netbird"):
                        await host("update", provider)
            except Exception as exc: log("watchdog.error", str(exc))

@asynccontextmanager
async def lifespan(app):
    init_storage(); task = asyncio.create_task(watchdog())
    yield
    task.cancel()

app = FastAPI(title="Z-Mesh Manager", version="0.2.0", lifespan=lifespan)
STATIC = APP_ROOT / "app" / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")

@app.get("/")
async def index(): return FileResponse(STATIC / "index.html")

@app.get("/api/health")
async def health(): return {"ok": True}

@app.get("/api/status")
async def status():
    try: return await host("audit")
    except Exception as exc: raise HTTPException(503, str(exc))

@app.get("/api/settings")
async def get_settings(): return settings()

@app.put("/api/settings")
async def put_settings(req: SettingsRequest):
    save_settings(req.model_dump()); return req

@app.post("/api/action")
async def action(req: ActionRequest):
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"id": job_id, "provider": req.provider, "action": req.action, "status": "queued", "progress": 0, "message": "Queued", "logs": []}
    asyncio.create_task(run_job(job_id, req.action, req.provider))
    return JOBS[job_id]

@app.post("/api/activate")
async def activate(req: ActivateRequest):
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"id": job_id, "provider": req.provider, "action": "connect", "status": "queued", "progress": 0, "message": "Queued", "logs": []}
    asyncio.create_task(run_job(job_id, "up", req.provider, req.credential, str(req.management_url) if req.management_url else None))
    return JOBS[job_id]

JOBS = {}

async def run_job(job_id, action, provider, credential=None, management_url=None):
    job = JOBS[job_id]; job.update(status="running", progress=2, message="Preparing")
    def update(pct, message):
        job.update(progress=pct, message=message); job["logs"].append(message); job["logs"] = job["logs"][-100:]
    try:
        result = await host(action, provider, credential, management_url, update)
        job.update(status="complete", progress=100, message="Complete", result=result)
    except Exception as exc:
        job.update(status="failed", message="Operation failed", error=str(exc), progress=max(job["progress"], 1))

@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    if job_id not in JOBS: raise HTTPException(404, "Job not found")
    return JOBS[job_id]

@app.get("/api/logs")
async def logs():
    path = DATA / "logs" / "manager.log"
    return {"lines": path.read_text(errors="replace").splitlines()[-200:] if path.exists() else []}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("ZMM_PORT", "8484")), proxy_headers=False)
