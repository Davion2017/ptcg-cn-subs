#!/usr/bin/env python3
"""Stage 1: download a YouTube video + its English ASR subtitle."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_settings, job_dir, log, run

def normalize_input(arg):
    """Accept a bare video id or any YouTube URL; return (video_id, url).

    Supported: watch?v=, youtu.be/, /shorts/, /live/, /embed/
    """
    import re
    arg = arg.strip()
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})", arg)
    if m:
        vid = m.group(1)
        return vid, f"https://www.youtube.com/watch?v={vid}"
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", arg):
        return arg, f"https://www.youtube.com/watch?v={arg}"
    raise SystemExit(f"看不懂这个输入，请给 YouTube 链接或 11 位视频 ID: {arg}")


def download(video_id, url=None):
    s = load_settings()["download"]
    video_id, url = normalize_input(video_id)
    d = job_dir(video_id)

    # 1) video + audio
    out_tpl = str(d / "source.%(ext)s")
    cmd = [
        "yt-dlp", url,
        "-f", s["format"],
        "--merge-output-format", "mp4",
        "-o", out_tpl,
        "--write-auto-subs", "--write-subs",
        "--sub-langs", s["sub_langs"],
        "--sub-format", "srt/vtt/best",
        "--convert-subs", "srt",
        "--write-info-json",
        "--no-playlist",
        "--no-warnings",
    ]
    log(f"[download] {video_id}")
    rc, out, err = run(cmd)
    if rc != 0:
        log(err[-2000:])
        raise SystemExit(f"yt-dlp failed ({rc})")

    src = next(d.glob("source.mp4"), None)
    if not src:
        raise SystemExit("no source.mp4 produced")

    # normalize subtitle filename
    subs = sorted(d.glob("source.*.srt"))
    target = d / "source.en.srt"
    picked = None
    for srt in subs:
        if ".en" in srt.name:
            picked = srt
            break
    if picked and picked != target:
        picked.rename(target)
    log(f"[download] done -> {src.name}, subs={'yes' if target.exists() else 'no'}")

    info = d / "source.info.json"
    if info.exists():
        meta = json.loads(info.read_text(encoding="utf-8"))
        keep = {k: meta.get(k) for k in
                ("id", "title", "upload_date", "duration", "uploader",
                 "uploader_id", "webpage_url", "description", "view_count")}
        (d / "meta.json").write_text(json.dumps(keep, ensure_ascii=False, indent=2), encoding="utf-8")
    return d

if __name__ == "__main__":
    download(sys.argv[1])
