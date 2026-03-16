"""
Forge Shorts — FastAPI Backend
Replaces routes-shorts.js with a Python service that reuses tracker.py and config.py directly.
Runs on port 5682, proxied by Nginx at /api/shorts/.
"""
import json
import logging
import re
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

import config
import tracker
from presets import PRESETS, DEFAULT_PRESET, FRAMING_MODES, CLIP_STYLES

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    tracker.init_db()
    log.info("Forge Shorts API started on port 5682")
    yield


app = FastAPI(title="Forge Shorts API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory settings (initialized from config + default preset) ────────────

_default_preset = PRESETS[DEFAULT_PRESET]
_settings = {
    "preset": DEFAULT_PRESET,
    "framing": _default_preset["framing"],
    "clipStyle": _default_preset["clipStyle"],
    "visionFrames": _default_preset["visionFrames"],
    "minDur": int(config.SEGMENT_MIN_DURATION),
    "targetDur": int(config.SEGMENT_TARGET_DURATION),
    "maxDur": int(config.SEGMENT_MAX_DURATION),
    "segCount": config.SEGMENT_TARGET_COUNT,
    "wordsPerGroup": config.SUBTITLE_WORDS_PER_GROUP,
}

ENV_PATH = Path(__file__).parent / ".env"

_SETTINGS_ENV_MAP = {
    "minDur": "SEGMENT_MIN_DURATION",
    "targetDur": "SEGMENT_TARGET_DURATION",
    "maxDur": "SEGMENT_MAX_DURATION",
    "segCount": "SEGMENT_TARGET_COUNT",
    "wordsPerGroup": "SUBTITLE_WORDS_PER_GROUP",
}


def _write_env(key: str, value: str):
    """Update or append a key=value in the .env file."""
    env_var = _SETTINGS_ENV_MAP.get(key)
    if not env_var:
        return
    if ENV_PATH.exists():
        text = ENV_PATH.read_text()
    else:
        text = ""
    pattern = re.compile(rf"^{re.escape(env_var)}=.*$", re.MULTILINE)
    new_line = f"{env_var}={value}"
    if pattern.search(text):
        text = pattern.sub(new_line, text)
    else:
        text = text.rstrip("\n") + f"\n{new_line}\n"
    ENV_PATH.write_text(text)


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/presets")
def get_presets():
    """Return all preset definitions + framing/clip mode metadata."""
    return {
        "presets": PRESETS,
        "framingModes": FRAMING_MODES,
        "clipStyles": CLIP_STYLES,
    }


@app.get("/jobs")
def list_jobs():
    return tracker.list_jobs()


@app.get("/jobs/{job_id}/segments")
def get_segments(job_id: int):
    return tracker.list_segments(job_id)


@app.get("/outputs")
def list_outputs():
    return tracker.list_completed_outputs()


@app.get("/download/{segment_id}")
def download(segment_id: int):
    path = tracker.get_segment_output_file(segment_id)
    if not path or not Path(path).is_file():
        raise HTTPException(status_code=404, detail="Output file not found")
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=Path(path).name,
    )


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".ts", ".mts", ".m4v"}


@app.get("/files")
def list_files():
    """List video files in the shorts inbox folder."""
    inbox = config.SHORTS_INBOX
    if not inbox.is_dir():
        return []
    files = []
    for f in sorted(inbox.iterdir()):
        if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS and not f.name.startswith("."):
            files.append({
                "name": f.name,
                "path": str(f),
                "size_mb": round(f.stat().st_size / (1024 * 1024), 1),
            })
    return files


@app.get("/settings")
def get_settings():
    return _settings


_VALID_FRAMING = set(FRAMING_MODES.keys())
_VALID_CLIP_STYLES = set(CLIP_STYLES.keys())


class SettingsUpdate(BaseModel):
    preset: Optional[str] = None
    framing: Optional[str] = None
    clipStyle: Optional[str] = None
    visionFrames: Optional[int] = None
    minDur: Optional[int] = None
    targetDur: Optional[int] = None
    maxDur: Optional[int] = None
    segCount: Optional[int] = None
    wordsPerGroup: Optional[int] = None


@app.post("/settings")
def update_settings(body: SettingsUpdate):
    updates = body.model_dump(exclude_none=True)

    # Validate preset
    if "preset" in updates and updates["preset"] not in PRESETS:
        raise HTTPException(400, f"Invalid preset '{updates['preset']}'. Valid: {list(PRESETS.keys())}")
    # Validate framing mode
    if "framing" in updates and updates["framing"] not in _VALID_FRAMING:
        raise HTTPException(400, f"Invalid framing '{updates['framing']}'. Valid: {list(_VALID_FRAMING)}")
    # Validate clip style
    if "clipStyle" in updates and updates["clipStyle"] not in _VALID_CLIP_STYLES:
        raise HTTPException(400, f"Invalid clipStyle '{updates['clipStyle']}'. Valid: {list(_VALID_CLIP_STYLES)}")
    # Validate numeric ranges
    if "visionFrames" in updates and not (0 <= updates["visionFrames"] <= 10):
        raise HTTPException(400, "visionFrames must be 0-10")
    if "segCount" in updates and not (1 <= updates["segCount"] <= 10):
        raise HTTPException(400, "segCount must be 1-10")
    if "wordsPerGroup" in updates and not (1 <= updates["wordsPerGroup"] <= 8):
        raise HTTPException(400, "wordsPerGroup must be 1-8")

    # If a preset is selected, apply its defaults first
    if "preset" in updates:
        p = PRESETS[updates["preset"]]
        _settings["preset"] = updates["preset"]
        _settings["framing"] = p["framing"]
        _settings["clipStyle"] = p["clipStyle"]
        _settings["visionFrames"] = p["visionFrames"]
        _settings["minDur"] = p["minDur"]
        _settings["targetDur"] = p["targetDur"]
        _settings["maxDur"] = p["maxDur"]
        _settings["segCount"] = p["segCount"]
        _settings["wordsPerGroup"] = p["wordsPerGroup"]
        # Then apply any additional overrides from the same request
        for key in ("framing", "clipStyle", "visionFrames", "minDur", "targetDur",
                     "maxDur", "segCount", "wordsPerGroup"):
            if key in updates and key != "preset":
                _settings[key] = updates[key]
    else:
        for key, value in updates.items():
            _settings[key] = value

    # Validate duration ordering
    if _settings["minDur"] > _settings["targetDur"]:
        _settings["targetDur"] = _settings["minDur"]
    if _settings["targetDur"] > _settings["maxDur"]:
        _settings["maxDur"] = _settings["targetDur"]

    # Persist duration/count settings to .env
    for key in ("minDur", "targetDur", "maxDur", "segCount", "wordsPerGroup"):
        if key in _settings:
            _write_env(key, str(_settings[key]))

    return _settings


class ProcessRequest(BaseModel):
    file: Optional[str] = None


@app.post("/process")
def trigger_process(body: ProcessRequest):
    if not body.file:
        raise HTTPException(status_code=400, detail="No file specified")
    file_path = Path(body.file)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {body.file}")

    # Pass current settings as JSON arg so orchestrate.py picks them up
    settings_json = json.dumps(_settings)
    subprocess.Popen(
        [sys.executable, str(Path(__file__).parent / "orchestrate.py"),
         str(file_path), "--settings", settings_json],
        cwd=str(Path(__file__).parent),
    )
    return {"status": "started", "file": body.file}


class WatcherRequest(BaseModel):
    active: bool


@app.post("/watcher")
def toggle_watcher(body: WatcherRequest):
    action = "start" if body.active else "stop"
    try:
        subprocess.run(
            ["sudo", "systemctl", action, "forge-shorts"],
            check=True,
            capture_output=True,
            timeout=10,
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"systemctl {action} failed: {e.stderr.decode()}")
    return {"active": body.active}


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5682)
