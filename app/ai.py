"""Claude-powered editing brain: finds the best short-form moments and writes the social copy."""
from __future__ import annotations

import json
import os

import anthropic

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")

CLIP_SCHEMA = {
    "type": "object",
    "properties": {
        "video_summary": {"type": "string"},
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "hook": {"type": "string"},
                    "on_screen_title": {"type": "string"},
                    "why_it_works": {"type": "string"},
                    "context_note": {"type": "string"},
                    "caption": {"type": "string"},
                    "first_comment": {"type": "string"},
                    "thumbnail_time": {"type": "number"},
                    "thumbnail_text": {"type": "string"},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "youtube_title": {"type": "string"},
                    "best_platforms": {"type": "array", "items": {"type": "string"}},
                    "score": {"type": "integer"},
                },
                "required": [
                    "title", "start", "end", "hook", "on_screen_title", "why_it_works", "context_note",
                    "caption", "first_comment", "thumbnail_time", "thumbnail_text", "hashtags", "youtube_title", "best_platforms", "score",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["video_summary", "clips"],
    "additionalProperties": False,
}

SYSTEM = """You are a senior social-media video editor for a nonprofit. You turn long recordings \
(interviews, events, talks, behind-the-scenes footage) into short vertical clips for Instagram Reels, \
TikTok, YouTube Shorts, Facebook and LinkedIn.

What makes a good clip:
- It stands on its own. Someone scrolling with no context must understand it. Never start mid-thought \
or on a pronoun whose referent is missing ("he", "that", "this program") unless the on-screen title \
supplies the missing context. Never end mid-sentence.
- It opens strong: the first 2-3 seconds carry a hook (a surprising line, an emotional moment, a question, \
a clear claim).
- It has one idea and a payoff: a story beat, a lesson, a moving moment, a call to action.
- It is faithful. Do not cut in a way that changes what the speaker meant or takes them out of context. \
If a moment needs context to be fair or understandable, say so in context_note and put the needed context \
into the on_screen_title or caption.

Copy guidelines: warm, human, genuine; no clickbait that the clip does not deliver; no invented facts, \
names, numbers or quotes that are not in the transcript. Captions should be 1-3 short sentences plus an \
optional call to action. Hashtags: 3-8, relevant, without the # sign.

first_comment: the first comment the account posts under its own post, to give people something to engage \
with. If the clip or caption asks people to act (donate, sign up, learn more), make the comment that action \
with the matching link. If the clip tells a story, make it the key statistic or a one-sentence summary of \
the story. 1-2 sentences. Only use links that appear in the brand details, exactly as written there; never \
invent or guess a URL. If no suitable link is given, leave the link out.

thumbnail_time and thumbnail_text: the cover image for the clip. You cannot see the video, so choose the \
moment from what is said: the key line or emotional peak, where the speaker is likely to look engaged. \
thumbnail_time is in seconds on the same timeline as start and end, inside the clip, and not in its first \
or last second. thumbnail_text is 2-6 words of cover text that would make someone tap.

Times: use the timestamps in the transcript (seconds). Start a clip at the start of a sentence and end it \
at the end of one. score is 1-100 for how likely the clip is to perform well."""


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _format_transcript(segments: list[dict]) -> str:
    return "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments)


def suggest_clips(segments: list[dict], duration: float, brand_context: str = "",
                  instructions: str = "", min_len: int = 15, max_len: int = 60, count: int = 5) -> dict:
    client = anthropic.Anthropic()
    user = f"""Video length: {duration:.1f} seconds.

About the organization / channel (use for tone and calls to action):
{brand_context or "(not provided)"}

Extra instructions from the editor:
{instructions or "(none)"}

Find up to {count} of the best clips, each between {min_len} and {max_len} seconds long. Clips may overlap \
only if they are clearly different edits. Order them best first. If the footage has fewer good moments, \
return fewer clips rather than weak ones.

Transcript with timestamps:
<transcript>
{_format_transcript(segments)}
</transcript>"""

    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM,
        messages=[{"role": "user", "content": user}],
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": CLIP_SCHEMA},
        },
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to analyse this transcript.")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Claude's answer was cut off; try asking for fewer clips.")
    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)
    return _clean(data, segments, duration, min_len, max_len)


def _clean(data: dict, segments: list[dict], duration: float, min_len: int, max_len: int) -> dict:
    clips = []
    for c in data.get("clips", []):
        start = max(0.0, float(c["start"]))
        end = min(duration, float(c["end"]))
        if end - start < 3:
            continue
        c["start"], c["end"] = round(start, 2), round(end, 2)
        c["hashtags"] = [h.lstrip("#").replace(" ", "") for h in c.get("hashtags", []) if h.strip()]
        c["score"] = max(1, min(100, int(c.get("score", 50))))
        tt = float(c.get("thumbnail_time") or 0)
        if not start + 0.5 <= tt <= end - 0.5:
            tt = start + (end - start) * 0.3
        c["thumbnail_time"] = round(tt, 1)
        clips.append(c)
    data["clips"] = clips
    return data


def heuristic_clips(segments: list[dict], duration: float, min_len: int = 15, max_len: int = 60,
                    count: int = 5) -> dict:
    """Fallback when no API key is configured: group whole sentences into clip-sized chunks."""
    clips, cur = [], []
    for s in segments:
        cur.append(s)
        length = cur[-1]["end"] - cur[0]["start"]
        if length >= min_len and (s["text"].rstrip()[-1:] in ".?!" or length >= max_len):
            text = " ".join(x["text"] for x in cur)
            clips.append({
                "title": text[:60] + ("..." if len(text) > 60 else ""),
                "start": cur[0]["start"], "end": cur[-1]["end"],
                "hook": cur[0]["text"], "on_screen_title": "", "why_it_works": "Auto-split by sentence (AI is off).",
                "context_note": "", "caption": text[:200], "first_comment": "",
                "thumbnail_time": round(cur[0]["start"] + length * 0.3, 1), "thumbnail_text": "",
                "hashtags": [], "youtube_title": text[:90],
                "best_platforms": [], "score": 50,
            })
            cur = []
    return {"video_summary": "AI suggestions are off because ANTHROPIC_API_KEY is not set. "
                             "These clips are simple sentence-based splits.", "clips": clips[:count]}
