#!/usr/bin/env python3
"""Stage 6: generate Bilibili title/description/tags and a cover frame."""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (load_settings, job_dir, log, run, provider_credentials)
from importlib import import_module
_t = import_module("30_translate") if False else None


def call(base, key, model, messages):
    import urllib.request
    body = {"model": model, "messages": messages, "temperature": 0.6, "max_tokens": 2000}
    req = urllib.request.Request(base + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)["choices"][0]["message"]["content"]


PROMPT = """你是 B 站宝可梦卡牌区 UP 主。根据给定的英文视频标题和简介，写一份中文投稿信息。

输出严格 JSON：
{"title":"<30字以内，带卡组核心，可用【】，不要夸张到虚假>",
 "desc":"<200字以内，说明卡组思路与看点；不要写来源和原链接，那部分由程序自动追加>",
 "tags":["<3到6个标签，不要#号>"],
 "cover_text":"<封面上要写的两行字，每行不超过8字>"}"""


def build(video_id):
    s = load_settings()
    d = job_dir(video_id)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8")) if (d / "meta.json").exists() else {}
    base, key = provider_credentials()
    user = json.dumps({
        "title": meta.get("title", ""),
        "description": (meta.get("description") or "")[:1200],
        "channel": meta.get("uploader", ""),
        "url": meta.get("webpage_url", ""),
    }, ensure_ascii=False)
    raw = call(base, key, s["provider"]["model"],
               [{"role": "system", "content": PROMPT}, {"role": "user", "content": user}])
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    try:
        obj = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.S)
        obj = json.loads(m.group(0))

    obj["source_url"] = meta.get("webpage_url", "")
    obj["source_channel"] = meta.get("uploader", "")

    # 简介尾部固定追加：机翻声明 + 来源。不交给模型写，保证每期都一致。
    body = (obj.get("desc") or "").strip()
    footer = (
        "\n\n"
        "⚠️ 本视频字幕由 AI 机器翻译，可能存在错译或术语不准，"
        "欢迎在评论区指正，会持续修正。\n"
        f"素材来源：YouTube 频道 {meta.get('uploader', '')}\n"
        f"原视频：{meta.get('webpage_url', '')}"
    )
    obj["desc"] = body + footer
    # 标题前缀在这里就加上，后面的 upload 阶段还会再校验一次
    base_title = (obj.get("title") or "").strip()
    for tag in ("【搬运】", "【自用】"):
        if base_title.startswith(tag):
            base_title = base_title[len(tag):].lstrip()
    obj["title"] = "【搬运】【自用】" + base_title
    (d / "bili.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"[meta] {obj.get('title')}")

    # cover frame at 20% into the video
    src = d / "source.mp4"
    if src.exists():
        dur = meta.get("duration") or 0
        ts = max(5, int(dur * 0.2)) if dur else 60
        cover = d / "cover_raw.jpg"
        run(["ffmpeg", "-y", "-ss", str(ts), "-i", str(src),
             "-frames:v", "1", "-q:v", "2", str(cover)])
        if cover.exists():
            log(f"[meta] cover frame at {ts}s -> {cover.name}")
    return obj


if __name__ == "__main__":
    build(sys.argv[1])
