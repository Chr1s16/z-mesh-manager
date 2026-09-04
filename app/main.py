import asyncio, os, time
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

app = FastAPI(title="Z-Mesh Manager", version="0.1.0", lifespan=lifespan)
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
    try: return await host(req.action, req.provider)
    except Exception as exc: raise HTTPException(500, str(exc))

@app.post("/api/activate")
async def activate(req: ActivateRequest):
    try: return await host("up", req.provider, req.credential, str(req.management_url) if req.management_url else None)
    except Exception as exc: raise HTTPException(500, str(exc))

@app.get("/api/logs")
async def logs():
    path = DATA / "logs" / "manager.log"
    return {"lines": path.read_text(errors="replace").splitlines()[-200:] if path.exists() else []}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("ZMM_PORT", "8484")), proxy_headers=False)
