#!/usr/bin/env python3
"""Stage 3.5: post-process the Chinese subtitle for artifacts and term drift."""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import job_dir, log, read_srt, write_srt, CONFIG

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
    write_srt(cues, d / "zh.clean.srt")
    (d / "zh.srt").write_text((d / "zh.clean.srt").read_text(encoding="utf-8"), encoding="utf-8")
    log(f"[cleanup] {changed}/{len(cues)} cues adjusted")

if __name__ == "__main__":
    run_cleanup(sys.argv[1])
