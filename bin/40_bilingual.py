#!/usr/bin/env python3
"""Stage 4: merge English + Chinese into a bilingual ASS subtitle."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_settings, job_dir, log, read_srt

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ZH,{font},{zsize},{zcolor},&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0.5,0,1,3.2,1.4,2,90,90,58,1
Style: EN,{font},{esize},{ecolor},&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0.5,0,1,2.6,1.2,2,90,90,26,1
"""


def ass_time(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def esc(text):
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def build(video_id):
    s = load_settings()["subtitle"]
    d = job_dir(video_id)
    zh = d / "zh.srt"
    en = d / "source.whisper.srt"
    if not en.exists():
        en = d / "source.en.srt"
    if not zh.exists() or not en.exists():
        raise SystemExit("need zh.srt and a source subtitle")

    zh_cues = {c["index"]: c for c in read_srt(zh)}
    en_cues = read_srt(en)

    header = ASS_HEADER.format(
        font=s["font"], zsize=s["font_size"], zcolor=s["zh_color"],
        esize=int(s["font_size"] * 0.62), ecolor=s["en_color"])

    events = []
    for i, e in enumerate(en_cues, 1):
        start, end = e["start"], e["end"]
        zh_text = zh_cues.get(i, {}).get("text", "")
        en_text = e["text"].replace("\n", " ")
        if not zh_text.strip():
            zh_text = ""
        if zh_text:
            events.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},ZH,,0,0,0,,{esc(zh_text)}")
        events.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},EN,,0,0,0,,{esc(en_text)}")

    out = d / "bilingual.ass"
    out.write_text(header + "\n[Events]\n"
                   "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
                   + "\n".join(events) + "\n", encoding="utf-8")
    log(f"[bilingual] {out.name}: {len(events)} dialogue lines")
    return out


if __name__ == "__main__":
    build(sys.argv[1])
