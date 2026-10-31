# KHF Clip Studio

Upload long videos (interviews, events, talks) and get ready-to-post short clips for Instagram Reels,
TikTok, YouTube Shorts, Facebook and LinkedIn.

**How it works**

1. **Upload** a video in the browser.
2. **Transcribe**: speech is transcribed on the server with word-level timing ([faster-whisper](https://github.com/SYSTRAN/faster-whisper), runs locally, free).
3. **Find clips**: Claude reads the transcript and suggests the strongest stand-alone moments, each with a hook,
   a "why it works" note, a **context check** (flags clips that could be misleading or confusing without context),
   an on-screen title, a caption, hashtags and a YouTube Shorts title. You can steer it ("moments about volunteers",
   "funny bits for TikTok") and set your organisation's voice once under **Brand settings**.
4. **Tweak and export**: adjust start and end, preview in the player, then export to 9:16, 1:1, 4:5 or 16:9 with
   animated word-by-word captions burned in. "Fill" crops to the speaker (with a crop-position slider); "Fit" keeps the
   whole shot over a blurred background.
5. You can also cut any range by hand from the **Transcript** tab, and download the full transcript as `.srt`.

## Run it

You need Python 3.10+ and `ffmpeg` installed.

```bash
pip install -r requirements.txt
cp .env.example .env            # then put your Anthropic API key in it
export $(grep -v '^#' .env | xargs)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000.

Or with Docker:

```bash
docker build -t khf-clip-studio .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... -v $PWD/data:/data khf-clip-studio
```

The first transcription downloads the Whisper model (about 500 MB for `small`). Without an API key the app still
works, but clip suggestions fall back to simple sentence-based splits.

## Deploy to Render (quickest test server)

1. Push this folder to a GitHub repo.
2. On [render.com](https://render.com), choose **New > Blueprint** and pick the repo. It reads `render.yaml`.
3. Paste your `ANTHROPIC_API_KEY` when asked. Render builds the Docker image and gives you a URL.

This uses the Starter plan with a 10 GB disk (roughly $7/month plus disk).

## Settings (environment variables)

| Variable | Default | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` | (none) | Turns on Claude clip suggestions and copywriting |
| `CLAUDE_MODEL` | `claude-opus-5-5` | Claude model used for analysis |
| `WHISPER_MODEL` | `small` | `tiny`/`base` are faster, `medium`/`large-v3` are more accurate |
| `WHISPER_DEVICE` | `auto` | Set to `cuda` on a GPU server for much faster transcription |
| `DATA_DIR` | `./data` | Where uploads, transcripts and exports are stored |
| `WORKERS` | `1` | How many videos/exports are processed at once (raise only on a bigger server) |

## Notes

- No login yet: run it on a private network or behind a password (e.g. your host's basic auth) before sharing a URL.
- Files are kept on the server's disk under `DATA_DIR`. Delete videos from the app to free space.
