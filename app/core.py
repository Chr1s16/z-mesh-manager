import asyncio, json, os, secrets, stat, time
from pathlib import Path

DATA = Path(os.getenv("ZMM_DATA_DIR", "/DATA/AppData/z-mesh-manager"))
APP_ROOT = Path(__file__).resolve().parent.parent
TOKEN_FILE = DATA / "config" / "api-token"
SETTINGS_FILE = DATA / "config" / "settings.json"
LOG_FILE = DATA / "logs" / "manager.log"
LOCK = asyncio.Lock()

def init_storage():
    for name in ("config", "state", "cache", "logs", "rollback", "locks"):
        (DATA / name).mkdir(parents=True, exist_ok=True)
    if not TOKEN_FILE.exists():
        _atomic(TOKEN_FILE, secrets.token_urlsafe(32))
        TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    if not SETTINGS_FILE.exists():
        _atomic(SETTINGS_FILE, json.dumps({"auto_repair": True, "automatic_updates": False, "update_check_hours": 24}, indent=2))

def _atomic(path: Path, value: str):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(value, encoding="utf-8")
    os.replace(tmp, path)

def settings():
    try: return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception: return {"auto_repair": True, "automatic_updates": False, "update_check_hours": 24}

def save_settings(value): _atomic(SETTINGS_FILE, json.dumps(value, indent=2))

def log(event: str, detail: str = ""):
    safe = detail.replace("tskey-", "[REDACTED]-").replace("setup-key", "credential")[:4000]
    with LOG_FILE.open("a", encoding="utf-8") as f: f.write(json.dumps({"time": int(time.time()), "event": event, "detail": safe}) + "\n")
    if LOG_FILE.stat().st_size > 2_000_000:
        LOG_FILE.replace(LOG_FILE.with_suffix(".log.1"))

async def host(action: str, provider: str = "all", secret: str | None = None, management_url: str | None = None):
    if action not in {"audit","install","repair","update","restart","up","down","rollback"}: raise ValueError("Unsupported action")
    if provider not in {"all","tailscale","netbird"}: raise ValueError("Unsupported provider")
    env = os.environ.copy(); env["ZMM_ACTION"] = action; env["ZMM_PROVIDER"] = provider
    if management_url: env["ZMM_MANAGEMENT_URL"] = management_url
    script = (APP_ROOT / "host" / "host-helper.sh").read_bytes()
    async with LOCK:
        proc = await asyncio.create_subprocess_exec("nsenter","-t","1","-m","-u","-n","-i","--","/bin/bash","-s", stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, env=env)
        payload = script + (b"\n" + secret.encode() if secret else b"\n")
        out, _ = await asyncio.wait_for(proc.communicate(payload), timeout=900)
    text = out.decode(errors="replace")
    log(f"{provider}.{action}", f"exit={proc.returncode} " + text[-1500:])
    if proc.returncode: raise RuntimeError(text[-2000:])
    try: return json.loads(text.strip().splitlines()[-1])
    except Exception: return {"ok": True, "output": text[-4000:]}
