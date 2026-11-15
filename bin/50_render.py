#!/usr/bin/env python3
"""Stage 5: burn the bilingual ASS subtitle into the video."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_settings, job_dir, log, run

def render(video_id):
    s = load_settings()["render"]
    d = job_dir(video_id)
    src = d / "source.mp4"
    ass = d / "bilingual.ass"
    if not src.exists() or not ass.exists():
        raise SystemExit("need source.mp4 and bilingual.ass")

    out = d / "final.mp4"
    vf = "subtitles=filename=" + ass.name.replace(":", r"\:")
    log("[render] burning subtitles")
    rc, _, err = run([
        "ffmpeg", "-y", "-i", str(src),
        "-vf", vf,
        "-c:v", "libx264", "-crf", str(s["crf"]), "-preset", s["preset"],
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", s["audio_bitrate"],
        "-movflags", "+faststart",
        str(out),
    ], cwd=str(d))
    if rc != 0:
        log(err[-2500:]); raise SystemExit("ffmpeg render failed")
    log(f"[render] done -> {out.name} ({out.stat().st_size/1e6:.1f} MB)")
    return out

if __name__ == "__main__":
    render(sys.argv[1])
