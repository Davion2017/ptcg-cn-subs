#!/usr/bin/env python3
"""Pipeline driver: run stages for one or more videos.

Usage:
  python bin/run.py 5SEUZlKhp0Y                 # all stages
  python bin/run.py "https://youtu.be/5SEUZlKhp0Y"   # URL also works
  python bin/run.py 5SEUZlKhp0Y --to 30         # stop after translate
  python bin/run.py --list batch1.json          # multiple ids
"""
import argparse, json, subprocess, sys
import re
from pathlib import Path

BIN = Path(__file__).resolve().parent


def normalize(arg):
    """YouTube URL or bare id -> 11-char video id."""
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})", arg)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", arg.strip()):
        return arg.strip()
    raise SystemExit(f"看不懂这个输入: {arg}")
STAGES = [
    ("10", "10_download.py"),
    ("20", "20_transcribe.py"),
    ("30", "30_translate.py"),
    ("35", "35_cleanup.py"),
    ("40", "40_bilingual.py"),
    # 45 reviews the subtitle and refuses to continue while it still has
    # untranslated text. Burning subtitles is the single expensive stage, so
    # nothing may be rendered until the text is confirmed clean.
    ("45", "45_review.py"),
    ("50", "50_render.py"),
    ("60", "60_meta.py"),
    ("70", "70_upload.py"),
]


def run_stage(script, vid, extra=()):
    print(f"\n=== {script} · {vid}", flush=True)
    p = subprocess.run([sys.executable, str(BIN / script), vid, *extra])
    if p.returncode != 0:
        raise SystemExit(f"stage {script} failed for {vid}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="*")
    ap.add_argument("--list", help="json file with video ids")
    ap.add_argument("--from", dest="start", default="10")
    ap.add_argument("--to", dest="end", default="60")
    ap.add_argument("--force", action="store_true", help="redo stages that have cached output")
    a = ap.parse_args()

    vids = [normalize(v) for v in a.videos]
    if a.list:
        vids += [normalize(v) for v in json.loads(Path(a.list).read_text())]
    if not vids:
        ap.error("no video ids")

    for vid in vids:
        for code, script in STAGES:
            if code < a.start or code > a.end:
                continue
            extra = ("--force",) if (a.force and code == "30") else ()
            run_stage(script, vid, extra)
    print("\nAll done.")


if __name__ == "__main__":
    main()
