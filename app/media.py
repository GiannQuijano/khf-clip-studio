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


CAPTION_STYLES = {
    # name: (font size as fraction of height, primary colour, highlight colour, uppercase, title box colour)
    # ASS colours are &HAABBGGRR. Kind Human Foundation: navy #2E3487, teal #74C0B6.
    "kind": (0.052, "&H00FFFFFF", "&H00B6C074", True, "&H0087342E"),   # white, active word KHF teal, navy title
    "bold": (0.055, "&H00FFFFFF", "&H0000E5FF", True, "&H00000000"),   # white, active word yellow
    "clean": (0.045, "&H00FFFFFF", "&H00FFFFFF", False, "&H00000000"), # plain white sentence case
}


def build_ass(words: list[dict], start: float, end: float, width: int, height: int,
              style: str = "kind", title: str | None = None, words_per_line: int = 3) -> str:
    """Build an ASS subtitle file with short, punchy word groups (social-media style).

    `words` are transcript words with absolute times; they are shifted to be relative to `start`.
    The word currently being spoken is highlighted.
    """
    size_frac, primary, highlight, upper, title_box = CAPTION_STYLES.get(style, CAPTION_STYLES["kind"])
    fs = int(height * size_frac) if height >= width else int(height * size_frac * 1.2)
    margin_v = int(height * (0.22 if height > width else 0.10))
    title_fs = int(fs * 0.8)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Inter,{fs},{primary},&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{max(3, fs // 12)},2,2,60,60,{margin_v},1
Style: Title,Inter,{title_fs},&H00FFFFFF,&H000000FF,{title_box},&HB4000000,-1,0,0,0,100,100,0,0,3,{max(8, title_fs // 4)},0,8,80,80,{int(height * 0.08)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    clip_len = end - start
    if title:
        lines.append(f"Dialogue: 1,{_ass_time(0)},{_ass_time(min(clip_len, 4.0))},Title,,0,0,0,,{_esc(title)}")

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
            lines.append(
                f"Dialogue: 0,{_ass_time(seg_start - start)},{_ass_time(min(seg_end, end) - start)},Cap,,0,0,0,,{text}"
            )
    return header + "\n".join(lines) + "\n"


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
    fx = min(max(focus_x, 0.0), 1.0)
    if framing == "fit":
        vf = (
            f"[0:v]split=2[bgsrc][fgsrc];"
            f"[bgsrc]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:5,eq=brightness=-0.08[bg];"
            f"[fgsrc]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )
    else:
        vf = (
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H}:(iw-{W})*{fx:.3f}:(ih-{H})/2,setsar=1"
        )
    if ass_path:
        ass = str(ass_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        vf += f",subtitles='{ass}'"
    vf += "[v]"
    cmd = [
        "ffmpeg", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(src),
        "-filter_complex", vf, "-map", "[v]",
    ]
    if has_audio:
        cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "160k"]
    cmd += [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-r", "30", "-movflags", "+faststart", str(dst),
    ]
    run(cmd)
