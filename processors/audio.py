"""音频 → Markdown：用 faster-whisper 转写。"""
import os, sys
from pathlib import Path

from faster_whisper import WhisperModel

_model_cache = {}


def _get_model(model_size="base"):
    if model_size not in _model_cache:
        sys.stderr.write(f"  加载 Whisper {model_size} ...\n")
        _model_cache[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _model_cache[model_size]


def process_audio(
    audio_path: str,
    output_path: str,
    config: dict | None = None,
) -> dict:
    config = config or {}
    model_size = config.get("whisper_model", "base")

    model = _get_model(model_size)

    sys.stderr.write(f"  转写 {audio_path} ...\n")
    segments, info = model.transcribe(audio_path, language="zh", beam_size=5)

    lines = [f"语言: {info.language} (概率 {info.language_probability:.2f})"]
    for seg in segments:
        start = format_time(seg.start)
        end = format_time(seg.end)
        lines.append(f"[{start} → {end}] {seg.text.strip()}")

    text = "\n".join(lines)
    Path(output_path).write_text(text, "utf-8", newline="\r\n")
    return {"status": "ok", "chars": len(text), "duration": round(info.duration, 1)}


def format_time(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"
