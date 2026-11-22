#!/usr/bin/env python3
"""Resolve a video's decklist to official CN names; check a subtitle against them.

Usage:
  python bin/chs_tools.py deck <video_id>       # print resolved deck + gaps
  python bin/chs_tools.py check <video_id>      # scan zh.clean.srt for drift
"""
import json, sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import job_dir, read_srt
import chs
import chs_verify


def cmd_deck(video_id):
    d = job_dir(video_id)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    desc = meta.get("description") or ""
    lines = chs.deck_lines(desc)
    resolved = chs_verify.resolve(desc)
    print(f"{meta.get('title')}\n{len(lines)} cards in decklist\n")
    missing = []
    for e in lines:
        zh = resolved.get(e["en"])
        mark = "  " if zh else "??"
        print(f" {mark} {e['count']} {e['en']:<32} {e['code']} {e['num']:>3} -> {zh}")
        if not zh:
            missing.append(e)
    print(f"\nresolved {len(lines)-len(missing)}/{len(lines)}")
    if missing:
        print("unresolved:", ", ".join(f"{m['en']} {m['code']} {m['num']}" for m in missing))


def cmd_check(video_id):
    d = job_dir(video_id)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    # Full deck for the video: dex join plus the verified trainer/energy names.
    # chs.deck_terms alone only covers Pokémon, so a check built on it reports
    # 0 drift while the subtitle is full of wrong trainer names.
    deck = chs_verify.resolve(meta.get("description") or "")
    official = sorted(set(deck.values()))
    srt = d / "zh.clean.srt"
    if not srt.exists():
        srt = d / "zh.srt"
    cues = read_srt(srt)
    join = "\n".join(c["text"] for c in cues)
    print(f"{len(cues)} cues, {len(deck)} official names expected")
    left = chs.english_leftovers(join, list(deck))
    print(f"english leftovers ({len(left)}): {', '.join(left[:15])}")
    fixes = chs.near_miss(join, official)
    print(f"near misses ({len(fixes)}):")
    for a, b in fixes:
        print(f"   {a} -> {b}")
    absent = [n for n in official if n not in join]
    print(f"official names never used ({len(absent)}): {', '.join(absent[:15])}")


if __name__ == "__main__":
    cmd = sys.argv[1]
    vid = sys.argv[2]
    {"deck": cmd_deck, "check": cmd_check}[cmd](vid)
