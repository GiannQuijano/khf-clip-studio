"""ffmpeg helpers: probing, audio extraction, thumbnails and vertical clip rendering."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ASPECTS = {
    "9:16": (1080, 1920),  # Reels / TikTok / Shorts
    "1:1": (1080, 1080),   # Feed posts
    "4:5": (1080, 1350),   # Instagram portrait feed
    "16:9": (1920, 1080),  # YouTube / LinkedIn landscape
}


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-1500:]}")


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    info = json.loads(out)
    video = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
    if not video:
        raise ValueError("No video stream found in the upload.")
    w, h = int(video["width"]), int(video["height"])
    rot = 0
    for sd in video.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = abs(int(sd["rotation"]))
    if rot in (90, 270):
        w, h = h, w
    return {"duration": float(info["format"]["duration"]), "width": w, "height": h, "has_audio": has_audio}


def extract_audio(src: Path, dst: Path) -> None:
    run(["ffmpeg", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)])


def thumbnail(src: Path, dst: Path, at: float = 1.0) -> None:
    run(["ffmpeg", "-y", "-ss", str(at), "-i", str(src), "-frames:v", "1", "-vf", "scale=480:-2", str(dst)])


# ---------- captions ----------

def _ass_time(t: float) -> str:
    t = max(t, 0)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def hex_to_ass(color: str) -> str:
    """'#RRGGBB' -> ASS '&H00BBGGRR' (ASS colours are blue-green-red)."""
    c = color.lstrip("#")
    return f"&H00{c[4:6]}{c[2:4]}{c[0:2]}".upper()


CAPTION_STYLES = {
    # name: (font size as fraction of height, primary colour, highlight colour, uppercase)
    # "accent" means the brand accent colour from Brand settings (KHF teal #5EC3B9 by default).
    "kind": (0.052, "&H00FFFFFF", "accent", True),      # white, active word in the brand accent colour
    "bold": (0.055, "&H00FFFFFF", "&H0000E5FF", True),  # white, active word yellow
    "clean": (0.045, "&H00FFFFFF", "&H00FFFFFF", False),  # plain white sentence case
}

TITLE_STYLES = {
    # name: (text colour, box colour or None for no box). "primary"/"accent" are the brand colours.
    "brand": ("&H00FFFFFF", "primary"),   # white on the brand primary colour (KHF navy)
    "accent": ("primary", "accent"),      # brand primary on the brand accent colour (navy on teal)
    "dark": ("&H00FFFFFF", "&H00000000"), # white on black
    "outline": ("&H00FFFFFF", None),      # white with a black outline, no box
}
TITLE_POSITIONS = {"top": 8, "middle": 5, "bottom": 2}  # ASS numpad alignment, centred
TITLE_SECONDS = 4.0


def build_ass(words: list[dict], start: float, end: float, width: int, height: int,
              style: str = "kind", title: str | None = None, words_per_line: int = 3,
              title_style: str = "brand", title_position: str = "top", colors: dict | None = None) -> str:
    """Build an ASS subtitle file with short, punchy word groups (social-media style).

    `words` are transcript words with absolute times; they are shifted to be relative to `start`.
    The word currently being spoken is highlighted. `colors` holds the brand "primary" and "accent"
    colours as #RRGGBB.
    """
    brand = {k: hex_to_ass(v) for k, v in {"primary": "#3C4292", "accent": "#5EC3B9", **(colors or {})}.items()}
    pick = lambda c: brand.get(c, c) if c else c  # noqa: E731
    size_frac, primary, highlight, upper = CAPTION_STYLES.get(style, CAPTION_STYLES["kind"])
    primary, highlight = pick(primary), pick(highlight)
    t_text, t_box = (pick(c) for c in TITLE_STYLES.get(title_style, TITLE_STYLES["brand"]))
    t_align = TITLE_POSITIONS.get(title_position, 8)

    fs = int(height * size_frac) if height >= width else int(height * size_frac * 1.2)
    margin_v = int(height * (0.22 if height > width else 0.10))
    title_fs = int(fs * 0.8)
    title_margin = int(height * (0.08 if height > width else 0.06))
    if t_box:  # opaque box: the "outline" colour fills the box
        t_style = f"{t_text},&H000000FF,{t_box},&HB4000000,-1,0,0,0,100,100,0,0,3,{max(8, title_fs // 4)},0"
    else:
        t_style = f"{t_text},&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{max(3, title_fs // 12)},2"
    # While a bottom title is showing, lift the captions above it so they don't overlap.
    lifted = margin_v + title_fs * 2 + int(height * 0.02) if height > width else title_margin + title_fs * 2 + int(height * 0.04)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Inter,{fs},{primary},&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{max(3, fs // 12)},2,2,60,60,{margin_v},1
Style: CapLifted,Inter,{fs},{primary},&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{max(3, fs // 12)},2,2,60,60,{max(margin_v, lifted)},1
Style: Title,Inter,{title_fs},{t_style},{t_align},80,80,{title_margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    clip_len = end - start
    title_end = min(clip_len, TITLE_SECONDS) if title else 0.0
    if title:
        lines.append(f"Dialogue: 1,{_ass_time(0)},{_ass_time(title_end)},Title,,0,0,0,,{_esc(title)}")
    lift = bool(title) and title_position == "bottom"

    ws = [w for w in words if w["end"] > start and w["start"] < end and w["word"].strip()]
    groups: list[list[dict]] = []
    cur: list[dict] = []
    for w in ws:
        cur.append(w)
        ends_sentence = w["word"].strip()[-1:] in ".?!,"
        if len(cur) >= words_per_line or ends_sentence:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)

    for gi, g in enumerate(groups):
        g_end = groups[gi + 1][0]["start"] if gi + 1 < len(groups) else g[-1]["end"]
        g_end = min(g_end, g[-1]["end"] + 0.6)
        for wi, w in enumerate(g):
            seg_start = w["start"]
            seg_end = g[wi + 1]["start"] if wi + 1 < len(g) else g_end
            if seg_end <= seg_start:
                continue
            parts = []
            for wj, other in enumerate(g):
                txt = _esc(other["word"].strip())
                if upper:
                    txt = txt.upper()
                if wj == wi and highlight != primary:
                    parts.append(f"{{\\c{highlight}}}{txt}{{\\c{primary}}}")
                else:
                    parts.append(txt)
            text = " ".join(parts)
            cap = "CapLifted" if lift and seg_start - start < title_end else "Cap"
            lines.append(
                f"Dialogue: 0,{_ass_time(seg_start - start)},{_ass_time(min(seg_end, end) - start)},{cap},,0,0,0,,{text}"
            )
    return header + "\n".join(lines) + "\n"


def _reframe(W: int, H: int, framing: str, fx: float) -> str:
    """filter_complex chain from [0:v] to a W x H picture (no output label)."""
    if framing == "fit":
        return (
            f"[0:v]split=2[bgsrc][fgsrc];"
            f"[bgsrc]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:5,eq=brightness=-0.08[bg];"
            f"[fgsrc]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )
    return (
        f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H}:(iw-{W})*{fx:.3f}:(ih-{H})/2,setsar=1"
    )


def frame(src: Path, dst: Path, t: float, aspect: str = "9:16", framing: str = "crop",
          focus_x: float = 0.5, best_of_window: bool = True) -> None:
    """Save a JPEG still at time t, framed like an export. With best_of_window, ffmpeg's thumbnail
    filter picks the most representative frame from the 2 seconds around t."""
    W, H = ASPECTS.get(aspect, ASPECTS["9:16"])
    fx = min(max(focus_x, 0.0), 1.0)
    # Shrink first so the frames held in memory by the thumbnail filter stay small.
    pre = "[0:v]scale=-2:'min(ih,1920)'[src];"
    vf = pre + _reframe(W, H, framing, fx).replace("[0:v]", "[src]", 1)
    if best_of_window:
        ss = max(0.0, t - 1.0)
        vf += ",thumbnail=30"
        cmd = ["ffmpeg", "-y", "-ss", f"{ss:.3f}", "-t", "2", "-i", str(src)]
    else:
        cmd = ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", str(src)]
    vf += "[v]"
    run(cmd + ["-filter_threads", "1", "-filter_complex", vf, "-map", "[v]", "-frames:v", "1", "-q:v", "2", str(dst)])


def render_clip(src: Path, dst: Path, start: float, end: float, aspect: str = "9:16",
                framing: str = "crop", ass_path: Path | None = None, focus_x: float = 0.5,
                has_audio: bool = True) -> None:
    """Cut [start, end] from src and reframe it for social media.

    framing:
      crop - fill the frame, cropping the sides (good for a single speaker); focus_x picks the
             horizontal centre of the crop (0 = left edge, 1 = right edge).
      fit  - keep the whole shot, centred over a blurred, zoomed copy of itself.
    """
    W, H = ASPECTS.get(aspect, ASPECTS["9:16"])
    vf = _reframe(W, H, framing, min(max(focus_x, 0.0), 1.0))
    if ass_path:
        ass = str(ass_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        vf += f",subtitles='{ass}'"
    vf += "[v]"
    cmd = [
        "ffmpeg", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(src),
        "-filter_threads", "1", "-filter_complex", vf, "-map", "[v]",
    ]
    if has_audio:
        cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "160k"]
    cmd += [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-threads", "2",
        "-r", "30", "-movflags", "+faststart", str(dst),
    ]
    run(cmd)
