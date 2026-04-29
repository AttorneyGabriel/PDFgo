"""视频 → Markdown：用 ffmpeg 提取音轨 + faster-whisper 转写。"""
import os, subprocess, sys, tempfile
from pathlib import Path

import imageio_ffmpeg

try:
    from .audio import process_audio
except ImportError:
    from processors.audio import process_audio


def process_video(
    video_path: str,
    output_path: str,
    config: dict | None = None,
) -> dict:
    """提取视频音轨为临时 WAV，交给 audio processor 转写。"""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_wav = tmp.name

    try:
        sys.stderr.write(f"  提取音轨 ...\n")
        subprocess.run(
            [ffmpeg, "-i", video_path, "-vn", "-acodec", "pcm_s16le",
             "-ar", "16000", "-ac", "1", "-y", tmp_wav],
            capture_output=True, timeout=600, check=True,
        )
        return process_audio(tmp_wav, output_path, config)
    finally:
        try:
            os.unlink(tmp_wav)
        except OSError:
            pass
