#!/usr/bin/env python3
"""Stage 3.5: post-process the Chinese subtitle for artifacts and term drift.

Besides the hand-written cleanup rules, this verifies card names against the
official CN dataset for the deck this video actually plays (bin/chs.py):
  - a fan translation that is one or two characters off gets corrected
  - English card names left untranslated get replaced
  - anything still suspicious is printed so a human can look
"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import job_dir, log, read_srt, write_srt, CONFIG
import chs
import chs_verify


def load_rules():
    p = CONFIG / "cleanup.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def clean(text, rules):
    reps = sorted(rules.get("replace", {}).items(), key=lambda kv: -len(kv[0]))
    for wrong, right in reps:
        text = text.replace(wrong, right)
    for pat, rep in rules.get("regex", []):
        text = re.sub(pat, rep, text)
    return text.strip()


def video_deck_terms(video_id):
    """Official CN names for the cards in this video's decklist."""
    if not chs.available():
        return {}
    meta_p = job_dir(video_id) / "meta.json"
    if not meta_p.exists():
        return {}
    try:
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    desc = meta.get("description") or ""
    return chs_verify.resolve(desc)


def run_cleanup(video_id):
    d = job_dir(video_id)
    src = d / "zh.srt"
    if not src.exists():
        raise SystemExit("no zh.srt")
    rules = load_rules()
    cues = read_srt(src)
    changed = 0
    for c in cues:
        new = clean(c["text"], rules)
        if new != c["text"]:
            changed += 1
            c["text"] = new

    # ---- official-name verification -------------------------------------
    deck = video_deck_terms(video_id)
    official = sorted(set(deck.values()))
    join = "\n".join(c["text"] for c in cues)

    # English names that never got translated
    leftovers = chs.english_leftovers(join, list(deck))
    en_fixed = 0
    if leftovers:
        for c in cues:
            for en in leftovers:
                if en in c["text"]:
                    c["text"] = c["text"].replace(en, deck[en])
                    en_fixed += 1
        log(f"[cleanup] english card names replaced: {en_fixed} "
            f"({', '.join(leftovers[:8])})")

    # Fan translations one or two characters off from the official name
    join = "\n".join(c["text"] for c in cues)
    fixes = chs.near_miss(join, official)
    nm_fixed = 0
    if fixes:
        for c in cues:
            for wrong, right in fixes:
                if wrong in c["text"]:
                    c["text"] = c["text"].replace(wrong, right)
                    nm_fixed += 1
        log(f"[cleanup] near-miss names fixed: {nm_fixed} "
            f"({', '.join(f'{a}->{b}' for a, b in fixes[:8])})")

    write_srt(cues, d / "zh.clean.srt")
    (d / "zh.srt").write_text((d / "zh.clean.srt").read_text(encoding="utf-8"),
                              encoding="utf-8")
    log(f"[cleanup] {changed}/{len(cues)} cues adjusted; "
        f"deck terms {len(deck)}, official names {len(official)}")

    # Remaining risk: log which official names never showed up at all
    join = "\n".join(c["text"] for c in cues)
    absent = [n for n in official if n not in join]
    if absent:
        log(f"[cleanup] deck cards not mentioned in subs: {len(absent)}")


if __name__ == "__main__":
    run_cleanup(sys.argv[1])
