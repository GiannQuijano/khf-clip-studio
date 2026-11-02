# Clip Studio: developer handoff

Clip Studio turns long videos into short social clips. You upload a video, it is transcribed on the
server, Claude picks the strongest stand-alone moments and writes captions, and you export vertical clips
with animated captions burned in. This copy is branded for Kind Human Foundation (KHF). Below is how it
works and how to set it up for a new client.

## What's in the package

```
app/
  main.py         FastAPI server: uploads, job queue, API routes, project storage (JSON on disk)
  transcribe.py   Speech-to-text with word timings (faster-whisper, runs locally, no API key)
  ai.py           Claude call: picks clips and writes copy (structured JSON output)
  media.py        ffmpeg: probe, audio extract, thumbnails, reframing, ASS caption styles
static/
  index.html      The studio UI (single page, vanilla JS, no build step)
  guide.html      "How it works" page for the client
  pricing.html    Running costs and billing handover page for the client
  brand.css       Brand tokens (colors, fonts) shared by all three pages
  logo.png        Logo for light backgrounds
  logo-white.png  Logo for dark backgrounds
demo/             Builds a clickable demo (real UI + fake server + drawn sample video) as one HTML file
Dockerfile        Production image (Python 3.12, ffmpeg, Inter font for captions)
render.yaml       One-click Render deploy (Standard plan + 10 GB disk)
```

## How a video flows through it

1. `POST /api/projects` saves the upload to `DATA_DIR/projects/<id>/` and queues `process()`.
2. `process()`: ffprobe, then a thumbnail, then 16 kHz mono WAV, then faster-whisper with word timestamps.
   The model is freed after each job to save memory.
3. `run_suggest()` sends the timestamped transcript plus the brand settings to Claude (`ai.py`, model
   `claude-opus-5-5`, structured JSON output, server-side refusal fallback). With no API key, it falls back
   to simple sentence-based splits.
4. `POST /api/projects/<id>/renders`: `media.render_clip()` cuts, reframes (crop or blurred-background
   fit, 9:16 / 4:5 / 1:1 / 16:9) and burns in an ASS subtitle file built from the word timings.
5. The UI polls `GET /api/projects/<id>` every 2 seconds while anything is running.

Jobs run one at a time (`WORKERS=1`) so a 2 GB server doesn't run out of memory. Unfinished jobs are
re-queued on restart; a video interrupted twice is marked as failed instead of looping.

## Run it locally

```bash
pip install -r requirements.txt          # also needs ffmpeg on PATH
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn app.main:app --reload --port 8000
```

Or `docker build -t clip-studio . && docker run -p 8000:8000 -e ANTHROPIC_API_KEY=... -v $PWD/data:/data clip-studio`.

The first transcription downloads the Whisper model from Hugging Face (about 500 MB for `small`).

## Set it up for a new client (rebranding checklist)

Do these in a fresh repo or a new branch. Search for `Kind Human`, `KHF` and `khf` to catch anything missed.

| What | Where | Change |
|---|---|---|
| Colors and fonts | `static/brand.css` | `--navy`/`--teal` and the light/dark token blocks at the top. `--accent` is the main button color; `--hl` is the highlight color. Fonts are loaded from Google Fonts in the `<link>` at the top of each HTML page. |
| Logo | `static/logo.png`, `static/logo-white.png` | Replace both. Transparent PNG, roughly 5:1, at least 60 px tall. The white version is for dark mode. |
| Page titles and names | `static/index.html`, `guide.html`, `pricing.html` | The `<title>`s, the `alt` text on the logos, and the tagline (`Your donations. Our mission. Their joy.`) in the empty state and footers. |
| Default brand voice | `app/main.py`, `DEFAULT_SETTINGS["brand_context"]` | Who the client is, the audience, the tone and the call to action. Users can also edit this in the app under **Brand settings** (saved to `DATA_DIR/settings.json`). |
| Caption colors | `app/media.py`, `CAPTION_STYLES["kind"]` | ASS colors are `&HAABBGGRR` (reversed). For example, teal `#74C0B6` becomes `&H00B6C074`. The 3rd value is the active word; the 5th is the title box. Rename the key (and its label in `index.html`, search `Kind Human (teal)`) if you like. |
| Guide content | `static/guide.html` | Mostly generic. Edit the Kind Human Foundation and clean-water examples (brand voice section, tips). |
| Pricing content | `static/pricing.html` | Update if the client uses a different host or plan. The "Moving the billing" section is written for Render + Anthropic. |
| Service name | `render.yaml` | `name: khf-clip-studio` sets the URL (`<name>.onrender.com`). |
| Demo page | `demo/shim-before.js` | Sample transcript, suggested clips and summary. Rebuild with `python3 demo/build.py out.html`. |

## Deploy (Render)

1. Push to a GitHub repo.
2. Render: **New > Blueprint**, pick the repo, paste `ANTHROPIC_API_KEY`. Or create a **Web Service** by
   hand: Docker, **Standard** plan (2 GB), env vars `ANTHROPIC_API_KEY`, `DATA_DIR=/data`,
   `WHISPER_MODEL=small`, a disk at `/data` (10 GB), health check `/api/config`.
3. Each push to `main` redeploys. Expect about a minute of 502 errors during a deploy, because services
   with a disk can't do zero-downtime deploys.

Use the client's own Anthropic API key, and set a monthly spend limit in the Anthropic Console.

## Environment variables

| Variable | Default | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | Required for Claude suggestions |
| `CLAUDE_MODEL` | `claude-opus-5-5` | |
| `WHISPER_MODEL` | `small` | `base` for less memory, `medium`/`large-v3` for accuracy on bigger servers |
| `WHISPER_DEVICE` | `auto` | `cuda` on a GPU server |
| `WHISPER_THREADS` | `2` | CPU threads for transcription |
| `WORKERS` | `1` | Parallel jobs. Raise only with more than 2 GB of memory |
| `DATA_DIR` | `./data` | Uploads, transcripts, exports, settings |

## Costs (October 2026 prices)

Render Standard $25/month, 10 GB disk $2.50/month, and Claude about $0.03–0.20 per video. A typical
month is $30–40. Details are in `static/pricing.html`.

## Known limits and good next steps

- **No login.** Anyone with the URL can use it. Simplest fix: HTTP basic auth middleware in `main.py`
  driven by an env var, or put it behind the host's access control.
- **Storage is local disk**, so it's a single instance. For scale, move uploads and exports to S3 or R2
  and the job queue to a worker.
- **Fixed crop position** per clip, with no automatic speaker tracking.
- **No automated tests yet.** The pipeline was checked end to end with a stubbed transcriber, and in
  production with real footage.
- Captions are rendered with the Inter font, installed in the Docker image (`fonts-inter`).
