"""KHF Clip Studio: upload long videos, get AI-picked short clips for social media."""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import ai, media
from .transcribe import release as release_model, transcribe

DATA = Path(os.environ.get("DATA_DIR", "./data")).resolve()
PROJECTS = DATA / "projects"
PROJECTS.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = DATA / "settings.json"
STATIC = Path(__file__).resolve().parent.parent / "static"

# The brand profile Claude writes for. Every field can be edited in the app under Brand settings.
DEFAULT_BRAND = {
    "org_name": "Kind Human Foundation",
    "mission": "The Kind Human Foundation exists to bring clean, life-giving water to communities living in "
               "survival mode, where the need is greatest and the impact is immediate.",
    "vision": "Seeing and serving the most forgotten through the power of clean water.",
    "audience": "Current and potential donors and supporters.",
    "tone": "Uplifting, hopeful, genuine, authentic, personable, reliable.",
    "tagline": "Clean water. Big change.",
    "supporter_benefit": "An opportunity to save a life that's overlooked.",
    "cta": "Donate, or learn more at kindhumanfoundation.com.",
    "links": "Website and donations: kindhumanfoundation.com",
    "avoid": "Pity, guilt or shock. Show real people and real impact, with dignity. Never invent facts or numbers.",
    "hashtags": "",
    "primary_color": "#3C4292",
    "accent_color": "#5EC3B9",
}
DEFAULT_SETTINGS = DEFAULT_BRAND | {"brand_context": "", "min_len": 15, "max_len": 60, "count": 5}

# The single free-text brand description used before Brand settings had separate fields. If a saved
# settings file still holds it unchanged, it is dropped so it doesn't contradict the new profile.
OLD_DEFAULT_CONTEXT = (
    "Kind Human Foundation funds practical, lasting clean-water solutions, such as wells and "
    "borewells, in communities where safe water is hardest to reach. Tagline: Your donations. "
    "Our mission. Their joy. Audience: current and potential donors and supporters. Tone: warm, "
    "hopeful, genuine, grateful; show real people and real impact, never pity. Usual call to "
    "action: donate or learn more at kindhumanfoundation.com."
)

BRAND_LABELS = [
    ("org_name", "Organization"),
    ("mission", "Mission"),
    ("vision", "Vision"),
    ("audience", "Audience"),
    ("tone", "Tone of voice"),
    ("tagline", "Tagline"),
    ("supporter_benefit", "What supporters get out of it"),
    ("cta", "Usual call to action"),
    ("links", "Links (use only these, exactly as written)"),
    ("avoid", "Avoid"),
    ("hashtags", "Hashtags to use when relevant"),
    ("brand_context", "Other notes"),
]


def brand_text(s: dict) -> str:
    """Turn the brand settings into the description Claude reads before picking clips."""
    return "\n".join(f"{label}: {str(s.get(key) or '').strip()}" for key, label in BRAND_LABELS
                     if str(s.get(key) or "").strip())


def brand_colors(s: dict) -> dict:
    return {"primary": s.get("primary_color") or DEFAULT_BRAND["primary_color"],
            "accent": s.get("accent_color") or DEFAULT_BRAND["accent_color"]}


app = FastAPI(title="KHF Clip Studio")
# One job at a time by default: transcription and video encoding each use a lot of memory, and running
# them side by side can exceed a 2 GB server. Raise WORKERS on a bigger instance.
pool = ThreadPoolExecutor(max_workers=int(os.environ.get("WORKERS", "1")))
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


# ---------------- storage helpers ----------------

def _lock(pid: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(pid, threading.Lock())


def _pdir(pid: str) -> Path:
    if not pid.isalnum():
        raise HTTPException(404, "Not found")
    d = PROJECTS / pid
    if not d.exists():
        raise HTTPException(404, "Project not found")
    return d


def load(pid: str) -> dict:
    return json.loads((_pdir(pid) / "project.json").read_text())


def save(p: dict) -> None:
    path = PROJECTS / p["id"] / "project.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(p, indent=1))
    tmp.replace(path)


def update(pid: str, fn) -> dict:
    with _lock(pid):
        p = load(pid)
        fn(p)
        save(p)
        return p


def settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    if SETTINGS_FILE.exists():
        saved = json.loads(SETTINGS_FILE.read_text())
        if saved.get("brand_context", "").strip() == OLD_DEFAULT_CONTEXT:
            saved["brand_context"] = ""
        s.update(saved)
    return s


def public(p: dict) -> dict:
    out = {k: v for k, v in p.items() if k not in ("words",)}
    return out


# ---------------- background jobs ----------------

def set_status(pid: str, status: str, progress: float | None = None, error: str | None = None):
    def fn(p):
        p["status"] = status
        if progress is not None:
            p["progress"] = round(progress, 3)
        p["error"] = error
    update(pid, fn)


def run_suggest(pid: str, opts: dict):
    p = load(pid)
    s = settings()
    brand = brand_text(s)
    min_len = int(opts.get("min_len") or s["min_len"])
    max_len = int(opts.get("max_len") or s["max_len"])
    count = int(opts.get("count") or s["count"])
    if not p["segments"]:
        result = {"video_summary": "No speech was detected, so there is nothing to base clips on. "
                                   "You can still cut clips manually.", "clips": []}
    elif ai.available():
        result = ai.suggest_clips(p["segments"], p["duration"], brand, opts.get("instructions", ""),
                                  min_len, max_len, count)
    else:
        result = ai.heuristic_clips(p["segments"], p["duration"], min_len, max_len, count)
    for c in result["clips"]:
        c["id"] = uuid.uuid4().hex[:8]

    def fn(p):
        p["summary"] = result.get("video_summary", "")
        p["suggestions"] = result["clips"]
        p["ai_used"] = ai.available()
    update(pid, fn)


def process(pid: str):
    try:
        update(pid, lambda p: p.update(attempts=p.get("attempts", 0) + 1))
        d = PROJECTS / pid
        p = load(pid)
        src = d / p["source"]
        set_status(pid, "probing", 0.02)
        info = media.probe(src)
        media.thumbnail(src, d / "thumb.jpg", at=min(1.0, info["duration"] / 2))
        update(pid, lambda p: p.update(info))
        segments, words, lang = [], [], None
        if info["has_audio"]:
            set_status(pid, "transcribing", 0.05)
            media.extract_audio(src, d / "audio.wav")
            try:
                tr = transcribe(d / "audio.wav", on_progress=lambda f: set_status(pid, "transcribing", 0.05 + 0.75 * f))
            finally:
                release_model()
            segments, words, lang = tr["segments"], tr["words"], tr["language"]
            (d / "audio.wav").unlink(missing_ok=True)
        update(pid, lambda p: p.update(segments=segments, words=words, language=lang))
        set_status(pid, "finding clips", 0.85)
        run_suggest(pid, p.get("options", {}))
        set_status(pid, "ready", 1.0)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        set_status(pid, "error", error=str(e))


def do_render(pid: str, rid: str):
    try:
        d = PROJECTS / pid
        p = load(pid)
        r = next(r for r in p["renders"] if r["id"] == rid)
        W, H = media.ASPECTS[r["aspect"]]
        ass_path = None
        if r["captions"] or r.get("title"):
            words = p.get("words", []) if r["captions"] else []
            ass_path = d / f"{rid}.ass"
            ass_path.write_text(media.build_ass(words, r["start"], r["end"], W, H,
                                                r["caption_style"], r.get("title") or None,
                                                title_style=r.get("title_style", "brand"),
                                                title_position=r.get("title_position", "top"),
                                                colors=r.get("colors") or brand_colors(settings())))
        out = d / "renders" / f"{rid}.mp4"
        out.parent.mkdir(exist_ok=True)
        media.render_clip(d / p["source"], out, r["start"], r["end"], r["aspect"], r["framing"],
                          ass_path, r["focus_x"], p.get("has_audio", True))
        if ass_path:
            ass_path.unlink(missing_ok=True)
        status, err = "done", None
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        status, err = "error", str(e)

    def fn(p):
        for r in p["renders"]:
            if r["id"] == rid:
                r["status"], r["error"] = status, err
    update(pid, fn)


# ---------------- API ----------------

@app.get("/api/config")
def config():
    return {"ai": ai.available(), "model": ai.MODEL if ai.available() else None,
            "aspects": list(media.ASPECTS), "caption_styles": list(media.CAPTION_STYLES),
            "title_styles": list(media.TITLE_STYLES), "title_positions": list(media.TITLE_POSITIONS)}


@app.get("/api/settings")
def get_settings():
    return settings()


HEX = r"^#[0-9A-Fa-f]{6}$"


class SettingsIn(BaseModel):
    org_name: str = Field("", max_length=200)
    mission: str = Field("", max_length=2000)
    vision: str = Field("", max_length=2000)
    audience: str = Field("", max_length=1000)
    tone: str = Field("", max_length=1000)
    tagline: str = Field("", max_length=300)
    supporter_benefit: str = Field("", max_length=1000)
    cta: str = Field("", max_length=1000)
    links: str = Field("", max_length=2000)
    avoid: str = Field("", max_length=1000)
    hashtags: str = Field("", max_length=500)
    primary_color: str = Field(DEFAULT_BRAND["primary_color"], pattern=HEX)
    accent_color: str = Field(DEFAULT_BRAND["accent_color"], pattern=HEX)
    brand_context: str = Field("", max_length=4000)
    min_len: int = Field(15, ge=3, le=600)
    max_len: int = Field(60, ge=5, le=900)
    count: int = Field(5, ge=1, le=20)


@app.put("/api/settings")
def put_settings(s: SettingsIn):
    SETTINGS_FILE.write_text(json.dumps(s.model_dump(), indent=1))
    return settings()


@app.get("/api/projects")
def list_projects():
    out = []
    for d in sorted(PROJECTS.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        f = d / "project.json"
        if f.exists():
            p = json.loads(f.read_text())
            out.append({k: p.get(k) for k in ("id", "name", "status", "progress", "duration", "created")}
                       | {"clips": len(p.get("suggestions", []))})
    return out


@app.post("/api/projects")
def create_project(file: UploadFile = File(...), instructions: str = Form("")):
    pid = uuid.uuid4().hex[:12]
    d = PROJECTS / pid
    d.mkdir(parents=True)
    ext = Path(file.filename or "video.mp4").suffix.lower() or ".mp4"
    if ext not in {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}:
        shutil.rmtree(d)
        raise HTTPException(400, "Please upload a video file (mp4, mov, m4v, webm, mkv, avi).")
    with open(d / f"source{ext}", "wb") as fh:
        shutil.copyfileobj(file.file, fh, length=4 * 1024 * 1024)
    p = {"id": pid, "name": file.filename, "source": f"source{ext}", "created": time.time(),
         "status": "queued", "progress": 0, "error": None, "segments": [], "words": [],
         "suggestions": [], "renders": [], "summary": "", "options": {"instructions": instructions}}
    save(p)
    pool.submit(process, pid)
    return public(p)


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    return public(load(pid))


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@app.patch("/api/projects/{pid}")
def rename_project(pid: str, body: RenameIn):
    name = " ".join(body.name.split())
    if not name:
        raise HTTPException(400, "The name can't be empty.")
    return public(update(pid, lambda p: p.update(name=name)))


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    shutil.rmtree(_pdir(pid))
    return {"ok": True}


class SuggestIn(BaseModel):
    instructions: str = ""
    min_len: int | None = None
    max_len: int | None = None
    count: int | None = None


@app.post("/api/projects/{pid}/retry")
def retry(pid: str):
    p = load(pid)
    if p["status"] != "error":
        raise HTTPException(409, "Only failed videos can be retried.")
    update(pid, lambda p: p.update(attempts=0))
    set_status(pid, "queued", 0)
    pool.submit(process, pid)
    return {"ok": True}


@app.post("/api/projects/{pid}/suggest")
def resuggest(pid: str, body: SuggestIn):
    p = load(pid)
    if p["status"] not in ("ready", "error"):
        raise HTTPException(409, "This video is still processing.")
    update(pid, lambda p: p.update(options=body.model_dump()))
    set_status(pid, "finding clips", 0.85)

    def job():
        try:
            run_suggest(pid, body.model_dump())
            set_status(pid, "ready", 1.0)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            set_status(pid, "ready", 1.0, error=f"Clip suggestions failed: {e}")
    pool.submit(job)
    return {"ok": True}


class RenderIn(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    aspect: str = "9:16"
    framing: str = "crop"
    captions: bool = True
    caption_style: str = "kind"
    title: str = ""
    title_style: str = "brand"
    title_position: str = "top"
    focus_x: float = Field(0.5, ge=0, le=1)
    label: str = ""


@app.post("/api/projects/{pid}/renders")
def create_render(pid: str, body: RenderIn):
    p = load(pid)
    if body.aspect not in media.ASPECTS:
        raise HTTPException(400, "Unknown aspect ratio")
    if body.title_style not in media.TITLE_STYLES or body.title_position not in media.TITLE_POSITIONS:
        raise HTTPException(400, "Unknown title style or position")
    end = min(body.end, p.get("duration") or body.end)
    if end - body.start < 1:
        raise HTTPException(400, "Clip must be at least 1 second long")
    rid = uuid.uuid4().hex[:10]
    r = body.model_dump() | {"id": rid, "end": end, "status": "rendering", "error": None, "created": time.time(),
                             "colors": brand_colors(settings())}
    update(pid, lambda p: p["renders"].insert(0, r))
    pool.submit(do_render, pid, rid)
    return r


@app.delete("/api/projects/{pid}/renders/{rid}")
def delete_render(pid: str, rid: str):
    d = _pdir(pid)
    (d / "renders" / f"{rid}.mp4").unlink(missing_ok=True)
    update(pid, lambda p: p.update(renders=[r for r in p["renders"] if r["id"] != rid]))
    return {"ok": True}


@app.get("/api/projects/{pid}/source")
def source(pid: str):
    p = load(pid)
    return FileResponse(_pdir(pid) / p["source"])


@app.get("/api/projects/{pid}/thumb")
def thumb(pid: str):
    f = _pdir(pid) / "thumb.jpg"
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(f)


@app.get("/api/projects/{pid}/frame")
def frame(pid: str, t: float, aspect: str = "9:16", framing: str = "crop", focus_x: float = 0.5,
          exact: int = 0, download: int = 0, name: str = "thumbnail"):
    """A still image for the clip's cover, framed like the export. Without `exact`, picks the most
    representative frame from the 2 seconds around `t` (avoids blinks and motion blur more often)."""
    d = _pdir(pid)
    p = load(pid)
    if aspect not in media.ASPECTS or framing not in ("crop", "fit"):
        raise HTTPException(400, "Unknown format")
    t = round(min(max(t, 0.0), max(0.0, (p.get("duration") or t) - 0.1)), 1)
    fx = round(min(max(focus_x, 0.0), 1.0), 2)
    out = d / "frames" / f"{t:.1f}_{aspect.replace(':', 'x')}_{framing}_{fx:.2f}_{1 if exact else 0}.jpg"
    if not out.exists():
        out.parent.mkdir(exist_ok=True)
        media.frame(d / p["source"], out, t, aspect, framing, fx, best_of_window=not exact)
    base = "".join(ch if ch.isalnum() or ch in " -_" else "" for ch in name).strip()[:50] or "thumbnail"
    return FileResponse(out, media_type="image/jpeg",
                        filename=f"{base}-{aspect.replace(':', 'x')}.jpg" if download else None)


@app.get("/api/projects/{pid}/renders/{rid}/file")
def render_file(pid: str, rid: str, download: int = 0):
    if not rid.isalnum():
        raise HTTPException(404)
    f = _pdir(pid) / "renders" / f"{rid}.mp4"
    if not f.exists():
        raise HTTPException(404)
    p = load(pid)
    r = next((r for r in p["renders"] if r["id"] == rid), {})
    base = "".join(ch if ch.isalnum() or ch in " -_" else "" for ch in (r.get("label") or "clip")).strip()[:50]
    name = f"{base or 'clip'}-{r.get('aspect', '').replace(':', 'x')}.mp4"
    return FileResponse(f, media_type="video/mp4", filename=name if download else None)


@app.get("/api/projects/{pid}/transcript.srt")
def transcript_srt(pid: str):
    from fastapi.responses import PlainTextResponse

    p = load(pid)

    def ts(t):
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    body = "\n".join(f"{i}\n{ts(s['start'])} --> {ts(s['end'])}\n{s['text']}\n"
                     for i, s in enumerate(p["segments"], 1))
    return PlainTextResponse(body, headers={"Content-Disposition": 'attachment; filename="transcript.srt"'})


@app.on_event("startup")
def resume_unfinished():
    """Re-queue work that was interrupted by a server restart."""
    for d in PROJECTS.iterdir():
        f = d / "project.json"
        if not f.exists():
            continue
        p = json.loads(f.read_text())
        if p["status"] not in ("ready", "error"):
            if p.get("attempts", 0) >= 2:
                # It was interrupted twice (usually the server running out of memory): stop retrying.
                set_status(p["id"], "error", error="Processing was interrupted twice, most likely because the "
                           "server ran out of memory. Try a shorter video, or a bigger server.")
            else:
                pool.submit(process, p["id"])
        for r in p.get("renders", []):
            if r["status"] == "rendering":
                pool.submit(do_render, p["id"], r["id"])


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
