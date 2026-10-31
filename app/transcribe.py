"""Speech-to-text with word timestamps using faster-whisper (runs locally, no API key needed)."""
from __future__ import annotations

import os
import threading
from pathlib import Path

_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel

            name = os.environ.get("WHISPER_MODEL", "small")
            device = os.environ.get("WHISPER_DEVICE", "auto")
            compute = "int8" if device in ("auto", "cpu") else "float16"
            _model = WhisperModel(name, device=device, compute_type=compute)
        return _model


def transcribe(audio_path: Path, on_progress=None) -> dict:
    """Returns {"language", "segments": [{start, end, text}], "words": [{start, end, word}]}."""
    model = _get_model()
    seg_iter, info = model.transcribe(str(audio_path), word_timestamps=True, vad_filter=True)
    segments, words = [], []
    total = info.duration or 1
    for seg in seg_iter:
        segments.append({"start": round(seg.start, 2), "end": round(seg.end, 2), "text": seg.text.strip()})
        for w in seg.words or []:
            words.append({"start": round(w.start, 2), "end": round(w.end, 2), "word": w.word})
        if on_progress:
            on_progress(min(seg.end / total, 1.0))
    return {"language": info.language, "segments": segments, "words": words}
