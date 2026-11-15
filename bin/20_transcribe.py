#!/usr/bin/env python3
"""Stage 2: obtain an accurate English transcript.

Strategy: YouTube ASR is a decent baseline but mangles card names. Re-run
Whisper locally (Apple Silicon / MLX) with a PTCG-aware initial prompt, then
use the YT ASR only as a cross-check/reference.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_settings, job_dir, log, run, read_srt, write_srt, ROOT

PROMPT = (
    "Pokemon Trading Card Game commentary. Terms: Pokemon ex, Pidgeot Control, "
    "Black Bolt, White Flare, Mega Evolution, bench, active, prize cards, "
    "knockout, retreat, ability, stage 2, trainer, supporter, stadium, "
    "energy acceleration, mill, stall, lock, aggro, meta, matchup. "
    "Card names: Pidgeot, Durant, Kangaskhan, Venusaur, Espeon, Dragapult."
)

def transcribe(video_id):
    s = load_settings()["whisper"]
    d = job_dir(video_id)
    src = d / "source.mp4"
    if not src.exists():
        raise SystemExit("run 10_download.py first")
    audio = d / "audio.wav"

    if not audio.exists():
        log("[audio] extracting 16k mono")
        rc, out, err = run(["ffmpeg", "-y", "-i", str(src), "-vn",
                            "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio)])
        if rc != 0:
            log(err[-1500:]); raise SystemExit("ffmpeg audio extract failed")

    out_dir = d / "whisper"
    out_dir.mkdir(exist_ok=True)
    log(f"[whisper] model={s['model']}")
    rc, out, err = run([
        "mlx_whisper", str(audio),
        "--model", s["model"],
        "--language", s["language"],
        "--output-dir", str(out_dir),
        "--output-name", "asr",
        "--output-format", "srt",
        "--initial-prompt", PROMPT,
        "--word-timestamps", "True",
        "--condition-on-previous-text", "False",
    ])
    if rc != 0:
        log(err[-2500:]); raise SystemExit("mlx_whisper failed")

    produced = out_dir / "asr.srt"
    if not produced.exists():
        raise SystemExit("whisper produced no srt")

    cues = read_srt(produced)
    write_srt(cues, d / "source.whisper.srt")
    log(f"[whisper] {len(cues)} cues")

    # keep YT ASR as reference if present
    yt = d / "source.en.srt"
    if yt.exists():
        (d / "source.ytasr.srt").write_text(yt.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    (d / "transcript.json").write_text(json.dumps(
        {"engine": "mlx-whisper", "model": s["model"], "cues": len(cues)},
        ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    transcribe(sys.argv[1])
