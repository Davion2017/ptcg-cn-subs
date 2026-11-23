#!/usr/bin/env python3
"""Stage 5: burn the bilingual ASS subtitle into the video.

Rendering is the expensive stage, so this refuses to run until:
  - 45_review.py has passed for the current zh.clean.srt, and
  - bilingual.ass actually exists and is newer than the reviewed subtitle.
It also skips the work entirely when neither the ASS nor the encode settings
changed since the last successful render.
"""
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_settings, job_dir, log, run


def digest(*paths, extra=""):
    h = hashlib.sha256()
    for p in paths:
        p = Path(p)
        if p.exists():
            h.update(p.read_bytes())
    h.update(extra.encode())
    return h.hexdigest()


def check_review(d):
    """Fail loudly instead of burning subtitles nobody verified."""
    review = d / "review.json"
    srt = d / "zh.clean.srt"
    if not review.exists():
        raise SystemExit("[render] blocked: run 45_review.py first "
                         "(no review.json)")
    if srt.exists() and review.stat().st_mtime < srt.stat().st_mtime:
        raise SystemExit("[render] blocked: zh.clean.srt is newer than "
                         "review.json — rerun 45_review.py")
    try:
        rep = json.loads(review.read_text(encoding="utf-8"))
    except Exception as e:
        raise SystemExit(f"[render] blocked: unreadable review.json ({e})")
    if not rep.get("ok"):
        raise SystemExit("[render] blocked: 45_review.py reported problems; "
                         "fix the cues it listed and rerun it")
    return rep


def render(video_id, force=False):
    s = load_settings()["render"]
    d = job_dir(video_id)
    src = d / "source.mp4"
    ass = d / "bilingual.ass"
    if not src.exists() or not ass.exists():
        raise SystemExit("need source.mp4 and bilingual.ass")

    rep = check_review(d)
    out = d / "final.mp4"
    marker = d / "render.json"
    fp = digest(ass, extra=json.dumps(s, sort_keys=True))

    if out.exists() and marker.exists() and not force:
        try:
            prev = json.loads(marker.read_text(encoding="utf-8"))
        except Exception:
            prev = {}
        if prev.get("fingerprint") == fp and prev.get("size") == out.stat().st_size:
            log("[render] subtitle and settings unchanged since the last "
                "render — skipping (use --force to redo)")
            return out

    log(f"[render] reviewed: {rep.get('cues')} cues, "
        f"auto-fixed {rep.get('auto_fixed')}")
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
    marker.write_text(json.dumps({
        "fingerprint": fp,
        "size": out.stat().st_size,
        "ass_mtime": ass.stat().st_mtime,
        "cues": rep.get("cues"),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"[render] done -> {out.name} ({out.stat().st_size/1e6:.1f} MB)")
    return out


if __name__ == "__main__":
    vid = [a for a in sys.argv[1:] if not a.startswith("--")][0]
    render(vid, force="--force" in sys.argv)
