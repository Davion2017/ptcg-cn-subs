#!/usr/bin/env python3
"""Stage 4.5: audit the Chinese subtitle BEFORE anything gets rendered.

Burning subtitles is by far the most expensive stage (a 90-minute video takes
minutes of CPU and produces gigabytes), so every name and coverage problem must
be caught here instead of after the fact. This stage:

  1. auto-fixes what is mechanically fixable (untranslated card names, and fan
     translations or ASR mis-hearings that differ from the official CN name by
     one or two characters);
  2. reports what it cannot fix — cues left in pure English, cues mixing a long
     English run into Chinese — and exits non-zero so 50_render refuses to run.

Exit code 0 = clean, safe to render. 1 = problems, render blocked.
"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import job_dir, log, read_srt, write_srt, CONFIG
import chs
import chs_verify

CJK = re.compile(r"[\u4e00-\u9fff]")
# English inside 全角/半角括号 is the sanctioned 「中文名(English)」 form, drop it first
BRACKETED = re.compile(r"[(（][^)）]*[A-Za-z][^)）]*[)）]")
# a run of 3+ latin words left in Chinese prose is almost always a missed term
LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z'’.\-]*(?:\s+[A-Za-z][A-Za-z'’.\-]*){2,}")


def substantive_english(text):
    """English left after removing bracketed glosses and bare numbers."""
    t = BRACKETED.sub(" ", text)
    t = re.sub(r"\b\d+\b", " ", t)
    return t


def deck_for(video_id):
    d = job_dir(video_id)
    meta_p = d / "meta.json"
    desc = ""
    if meta_p.exists():
        try:
            desc = json.loads(meta_p.read_text(encoding="utf-8")).get("description") or ""
        except Exception:
            desc = ""
    try:
        return chs_verify.resolve_for(video_id)
    except Exception as e:
        log(f"[review] deck resolve failed: {e}")
        return {}


def review(video_id, auto_fix=True):
    d = job_dir(video_id)
    src = d / "zh.clean.srt"
    if not src.exists():
        src = d / "zh.srt"
    if not src.exists():
        raise SystemExit("no zh.srt; run 30_translate.py first")
    cues = read_srt(src)
    deck = deck_for(video_id)
    official = sorted(set(deck.values()))
    log(f"[review] {len(cues)} cues, {len(deck)} official names for this deck")

    fixed_en = fixed_nm = 0
    if auto_fix:
        for c in cues:
            t = c["text"]
            for en, zh in deck.items():
                if not en or len(en) < 4:
                    continue
                pat = r"(?<![A-Za-z])" + re.escape(en) + r"(?![A-Za-z])"
                for m in list(re.finditer(pat, t, re.I)):
                    before = t[max(0, m.start() - 2):m.start()]
                    if before.endswith("(") or before.endswith("（"):
                        continue
                    t = t[:m.start()] + zh + t[m.end():]
                    fixed_en += 1
                    break
            c["text"] = t
        join = "\n".join(c["text"] for c in cues)
        fixes = chs.near_miss(join, official)
        if fixes:
            for c in cues:
                for wrong, right in fixes:
                    if wrong in c["text"]:
                        c["text"] = c["text"].replace(wrong, right)
                        fixed_nm += 1
        if fixed_en or fixed_nm:
            write_srt(cues, d / "zh.clean.srt")
            (d / "zh.srt").write_text((d / "zh.clean.srt").read_text(encoding="utf-8"),
                                      encoding="utf-8")
    log(f"[review] auto-fixed: {fixed_en} untranslated name(s), "
        f"{fixed_nm} near-miss name(s)")

    # ---- blockers -------------------------------------------------------
    english_only, mixed = [], []
    for c in cues:
        t = (c["text"] or "").strip()
        if not t:
            continue
        if not CJK.search(t):
            # Short all-English cues are player nicknames, card shouts or
            # numbers — the deliverable deliberately keeps those. Only a real
            # sentence (4+ words) means the translator dropped the cue.
            rest = substantive_english(t).strip(" 。．.,，!！?？~～-—")
            if len(rest.split()) >= 4:
                english_only.append((c["index"], t))
        else:
            rest = substantive_english(t)
            m = LATIN_RUN.search(rest)
            if m and len(m.group(0)) >= 12:
                mixed.append((c["index"], m.group(0), t))

    bare = "\n".join(substantive_english(c["text"]) for c in cues)
    remaining = chs.english_leftovers(bare, list(deck))
    leftover_nm = chs.near_miss("\n".join(c["text"] for c in cues), official)

    ok = True
    if english_only:
        ok = False
        log(f"[review] BLOCK: {len(english_only)} cue(s) still pure English")
        for i, t in english_only[:8]:
            log(f"           #{i}: {t[:90]}")
    if mixed:
        ok = False
        log(f"[review] BLOCK: {len(mixed)} cue(s) keep a long English run")
        for i, run, t in mixed[:8]:
            log(f"           #{i}: {run!r} in {t[:70]}")
    if remaining:
        ok = False
        log(f"[review] BLOCK: card name(s) still in English: {', '.join(remaining[:10])}")
    if leftover_nm:
        ok = False
        log(f"[review] BLOCK: near-miss name(s) left: "
            f"{', '.join(f'{a}->{b}' for a, b in leftover_nm[:8])}")

    report = {
        "cues": len(cues),
        "deck_terms": len(deck),
        "auto_fixed": {"english": fixed_en, "near_miss": fixed_nm},
        "english_only": [{"i": i, "text": t} for i, t in english_only],
        "mixed": [{"i": i, "run": r, "text": t} for i, r, t in mixed],
        "english_leftovers": remaining,
        "near_misses": [{"got": a, "want": b} for a, b in leftover_nm],
        "ok": ok,
    }
    (d / "review.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                   encoding="utf-8")

    if ok:
        log("[review] PASS — subtitle is clean, safe to render")
        return True
    log("[review] FAIL — fix the cues above, then rerun 45_review.py "
        "(do NOT render yet)")
    return False


if __name__ == "__main__":
    vid = sys.argv[1]
    good = review(vid, auto_fix="--no-fix" not in sys.argv)
    sys.exit(0 if good else 1)
