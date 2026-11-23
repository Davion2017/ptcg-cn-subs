#!/usr/bin/env python3
"""Stage 3: translate English cues to Simplified Chinese, batched with context.

Card names must follow the official CN localisation. We feed a glossary and
translate in overlapping batches so tone stays continuous.
"""
import json, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (load_settings, job_dir, log, read_srt, write_srt,
                    provider_credentials, model_backend, CONFIG)
import glossary as gl_mod
import chs as chs_mod
import chs_verify

BATCH = 25          # cues per request
OVERLAP = 4         # cues of context carried into the next batch

SYSTEM = """你是宝可梦集换式卡牌（PTCG）的中文译者和字幕员。

绝对规则（违反即失败）：
1. 只输出 JSON：{"lines":[{"i":序号,"zh":"译文"},...]}，不要任何解释。
2. 所有宝可梦名、卡牌名、招式名、特性名、道具名，必须译成简体中文，禁止保留英文。
   题库（term = 中文）会在用户消息中给出，必须逐条遵守，包括拼错的近似词。
3. 如果某个英文专名在题库里找不到：
   - 是宝可梦/卡牌 → 用最接近的官方译名，并在括号里保留英文，如「流氓鳄(Krookodile)」；
   - 是选手名、频道名、UP 主名字 → 保留英文原样，不翻译。
4. 字幕里不能成段出现英文句子；英文只能是括号内的辅助信息。
5. 竞技术语用中文圈说法：meta→环境、rogue deck→非主流卡组、mill→磨牌、stall→拖延、
   lock→锁场、bench→后备区、active→前场、prize→奖品卡、KO→击倒、spread→散布、
   aggro→快攻、toolbox→工具箱卡组、tech→对策卡。
6. 每条译文 ≤ 34 个汉字，口语化，像中文 UP 主解说。
7. 数字与能量：3 energy→3个能量，1 psychic→1个超能量。
8. 人称必须用标准汉字：you→你/你们，your opponent→对手/你的对手。
   严禁出现「酸奶」「哎哟」这类乱码词——出现即为错误。

示例：
英文: At number 9, we have Cobalion. This is a partial reprint of Cobalion EX from Plasma Storm.
正确: 第9名，勾帕路翁。这是等离子风暴里勾帕路翁EX的部分复刻。
错误: 第9名，Cobalion。这是 Plasma Storm 里 Cobalion EX 的部分复刻。"""


def load_glossary():
    return gl_mod.load()


def call_model(backend, messages, json_mode=True, retries=3):
    """Send one chat request to whatever backend is configured.

    Cloud = OpenAI-compatible /chat/completions with response_format json_object.
    Local = Ollama /api/chat with think=false (qwen3.5 thinks by default, which
    both wastes the context and breaks the JSON-only contract) and no structured
    output, because this Ollama build rejects `format` with the MLX runner.
    """
    import urllib.request
    if backend["mode"] == "local":
        body = {"model": backend["model"], "messages": messages,
                "stream": False, "think": False,
                "options": {"temperature": 0.1, "num_predict": 16000}}
        if backend.get("num_ctx"):
            body["options"]["num_ctx"] = backend["num_ctx"]
        url = backend["base"] + "/api/chat"
        headers = {"Content-Type": "application/json"}
    else:
        body = {"model": backend["model"], "messages": messages,
                "temperature": 0.1, "max_tokens": 16000}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        url = backend["base"] + "/chat/completions"
        headers = {"Content-Type": "application/json",
                   "Authorization": "Bearer " + backend["key"]}

    data = json.dumps(body).encode()
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=900) as r:
                resp = json.load(r)
            if backend["mode"] == "local":
                return resp["message"]["content"]
            return resp["choices"][0]["message"]["content"]
        except Exception as e:
            last = e
            import time as _t
            _t.sleep(2 * (attempt + 1))
    raise RuntimeError(f"model call failed: {last}")


def parse_json(text):
    """Parse model JSON defensively; also salvage a truncated lines array."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    # last resort: pull out complete {"i":..,"zh":".."} objects one by one
    lines = []
    for mm in re.finditer(r'\{\s*"i"\s*:\s*(\d+)\s*,\s*"zh"\s*:\s*"((?:[^"\\]|\\.)*)"\s*\}', text):
        try:
            lines.append({"i": int(mm.group(1)),
                          "zh": json.loads('"' + mm.group(2) + '"')})
        except Exception:
            continue
    if lines:
        return {"lines": lines}
    raise ValueError("unparseable model output")


def translate(video_id, force=False):
    s = load_settings()
    d = job_dir(video_id)
    src = d / "source.whisper.srt"
    if not src.exists():
        src = d / "source.en.srt"
    if not src.exists():
        raise SystemExit("no source subtitle; run 20_transcribe.py first")

    cues = read_srt(src)
    if not cues:
        raise SystemExit("empty subtitle")

    out = d / "zh.srt"
    if out.exists() and not force:
        log("[translate] exists, use --force to redo")
        return out

    backend = model_backend()
    model = backend["model"]
    glossary = load_glossary()
    log(f"[translate] {len(cues)} cues, model={model} ({backend['mode']}), "
        f"glossary={len(glossary)}")

    # Authoritative names for the deck this video actually plays, straight from
    # the official CN dataset. These win over anything in the hand glossary.
    deck = {}
    meta_p = d / "meta.json"
    if meta_p.exists() and chs_mod.available():
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            deck = chs_verify.resolve_for(video_id)
        except Exception as e:
            log(f"[translate] chs deck lookup failed: {e}")
    log(f"[translate] official CN names for this deck: {len(deck)}")

    results = {}
    i = 0
    while i < len(cues):
        batch = cues[i:i + BATCH]
        ctx_start = max(0, i - OVERLAP)
        ctx = cues[ctx_start:i]

        payload = []
        alias_hits = []
        for c in batch:
            raw_en = c["text"].replace("\n", " ")
            fixed_en = gl_mod.apply_aliases(raw_en)
            if fixed_en != raw_en:
                alias_hits.append(f"{raw_en.strip()}  →  实为: {fixed_en.strip()}")
            payload.append({"i": c["index"], "en": fixed_en})
        user = []
        if ctx:
            user.append("前文（仅作语境，不要翻译，不要输出）：")
            user.append("\n".join(f"[{c['index']}] {c['text']}" for c in ctx))
            user.append("")
        # terms relevant to THIS batch (exact + fuzzy hits on the raw English)
        batch_text = " ".join(c["text"] for c in batch)
        corrected = gl_mod.apply_aliases(batch_text)
        terms = {}
        for t in gl_mod.exact_terms(corrected):
            terms[t] = glossary[t]
        for orig, matched, zh in gl_mod.fuzzy_terms(corrected):
            terms[orig] = zh
        if alias_hits:
            user.append("语音识别纠错（原文已按正确卡名改写，请照此翻译）：")
            user.extend(alias_hits)
            user.append("")
        merged_terms = dict(terms)
        merged_terms.update(deck)          # official CN names win
        if merged_terms:
            user.append("题库（term = 中文官方译名，必须逐条遵守；含拼写近似词）：")
            user.append("\n".join(f"{k} = {v}" for k, v in sorted(merged_terms.items())))
            user.append("")
        else:
            user.append("本段没有检测到卡名；若有英文专名请按规则 3 处理。")
            user.append("")
        user.append("请翻译下面这些字幕行，输出 JSON：")
        user.append(json.dumps({"lines": payload}, ensure_ascii=False))

        try:
            raw = call_model(backend,
                             [{"role": "system", "content": SYSTEM},
                              {"role": "user", "content": "\n".join(user)}])
            obj = parse_json(raw)
        except Exception as e:
            log(f"[translate] batch at {i} failed ({e}); retrying with smaller chunk")
            sub_ok = 0
            for c in batch:
                try:
                    r2 = call_model(backend,
                                    [{"role": "system", "content": SYSTEM},
                                     {"role": "user", "content":
                                      f"题库片段：\n" + "\n".join(f"{k} = {v}" for k, v in sorted(terms.items())[:40]) +
                                      "\n\n请翻译这一条，输出 JSON：\n" +
                                      json.dumps({"lines": [{"i": c["index"],
                                                 "en": c["text"].replace(chr(10), " ")}]}, ensure_ascii=False)}])
                    o2 = parse_json(r2)
                    for item in o2.get("lines", []):
                        results[int(item["i"])] = str(item["zh"]).strip()
                        sub_ok += 1
                except Exception:
                    continue
            log(f"[translate]   salvaged {sub_ok}/{len(batch)} individually")
            i += BATCH
            continue
        for item in obj.get("lines", []):
            try:
                results[int(item["i"])] = str(item["zh"]).strip()
            except Exception:
                continue
        log(f"[translate] {min(i + BATCH, len(cues))}/{len(cues)}")
        i += BATCH

    # The model sometimes drops lines from a batch; those cues would otherwise
    # ship as raw English. Re-ask for just the missing ones.
    gaps = [c for c in cues if not results.get(c["index"])]
    if gaps:
        log(f"[translate] {len(gaps)} cues came back untranslated; asking again")
        fixed = 0
        for c in gaps:
            try:
                r2 = call_model(backend,
                                [{"role": "system", "content": SYSTEM},
                                 {"role": "user", "content":
                                  "题库片段：\n" + "\n".join(f"{k} = {v}" for k, v in sorted(deck.items())[:40]) +
                                  "\n\n请翻译这一条，输出 JSON：\n" +
                                  json.dumps({"lines": [{"i": c["index"],
                                             "en": c["text"].replace(chr(10), " ")}]}, ensure_ascii=False)}])
                for item in parse_json(r2).get("lines", []):
                    zh = str(item.get("zh") or "").strip()
                    if zh:
                        results[int(item["i"])] = zh
                        fixed += 1
            except Exception as e:
                log(f"[translate]   cue {c['index']} still failed: {e}")
        log(f"[translate] gap pass filled {fixed}/{len(gaps)}")

    merged = []
    for c in cues:
        zh = results.get(c["index"], "")
        merged.append({"start": c["start"], "end": c["end"], "text": zh or c["text"]})

    write_srt(merged, out)
    missing = sum(1 for c in merged if c["text"] == "")
    log(f"[translate] wrote {out.name}, missing={missing}")
    return out


if __name__ == "__main__":
    vid = sys.argv[1]
    translate(vid, force="--force" in sys.argv)
