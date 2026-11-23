#!/usr/bin/env python3
"""Pin down official CN names for cards the dex join can't resolve.

Pokémon are resolved by national-dex number (bin/chs.py). Trainers, stadiums
and energy have no dex, and the CN dataset and the English dataset don't share
collector numbers, so instead we ask the model to pick from the official CN
name pool and *verify the answer is literally in that pool*. Anything the model
invents is rejected. Results are cached in config/chs_verified.json.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CONFIG, provider_credentials, load_settings, log, model_backend
import chs

CACHE = CONFIG / "chs_verified.json"


def _pool(idx):
    pool = set(idx.get("cn_cards", [])) | set(idx.get("cn_moves", []))
    for names in idx.get("set_cn", {}).values():
        pool.update(names)
    return {p for p in pool if p and "★" not in p}


def _cache():
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save(c):
    CACHE.write_text(json.dumps(c, ensure_ascii=False, indent=1, sort_keys=True),
                     encoding="utf-8")


def _ask(backend, en, pool_sorted):
    import urllib.request
    listing = "、".join(pool_sorted)
    sys_prompt = ("你是宝可梦卡牌（PTCG）简中官方译名词典。"
                  "只能从给定名单里选一个名字作为答案，不得自创、不得改动任何字。"
                  "实在没有对应项就回答 NONE。")
    user = (f"名单（官方简体中文卡名）：\n{listing}\n\n"
            f"英文卡名：{en}\n"
            f"请只输出名单里与它对应的那一个名字，不要解释。")
    messages = [{"role": "system", "content": sys_prompt},
                {"role": "user", "content": user}]

    if backend["mode"] == "local":
        body = {"model": backend["model"], "messages": messages,
                "stream": False, "think": False,
                "options": {"temperature": 0, "num_predict": 200}}
        if backend.get("num_ctx"):
            body["options"]["num_ctx"] = backend["num_ctx"]
        url = backend["base"] + "/api/chat"
        headers = {"Content-Type": "application/json"}
    else:
        body = {"model": backend["model"], "temperature": 0, "messages": messages}
        url = backend["base"] + "/chat/completions"
        headers = {"Content-Type": "application/json",
                   "Authorization": "Bearer " + backend["key"]}

    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers=headers)
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.load(r)
    if backend["mode"] == "local":
        return (resp["message"]["content"] or "").strip()
    return (resp["choices"][0]["message"]["content"] or "").strip()


def resolve(description, force=False):
    """EN name -> verified official CN name, for every decklist card."""
    idx = chs.load()
    pool = _pool(idx)
    pool_sorted = sorted(pool)
    cache = _cache()
    terms, unverified = {}, []

    for d in chs.deck_lines(description):
        en = d["en"]
        zh = chs.official_name(en, d["code"], d["num"], idx)
        if zh:
            terms[en] = zh
            continue
        if not force and en in cache:
            if cache[en]:
                terms[en] = cache[en]
            else:
                unverified.append(en)
            continue
        unverified.append(en)

    # A cached None means "the model couldn't find it", not "there is no name".
    # Re-ask when the dex path has since started resolving it, which happens
    # after fixes to chs.py; otherwise stale negative cache hides the answer.
    if unverified and not force:
        retry = [en for en in unverified if en in cache and cache[en] is None]
        if retry:
            unverified = retry + [en for en in unverified if en not in cache]

    if unverified:
        backend = model_backend()
        resolved, rejected = 0, []
        for en in unverified:
            try:
                ans = _ask(backend, en, pool_sorted)
            except Exception as e:
                log(f"[chs] {en}: model call failed ({e})")
                continue
            ans = ans.strip().strip("。.,，\"'“”")
            if ans in pool:
                cache[en] = ans
                terms[en] = ans
                resolved += 1
            else:
                cache[en] = None
                rejected.append((en, ans))
        _save(cache)
        log(f"[chs] verified {resolved} extra names, "
            f"{len(rejected)} not in official pool")
        for en, ans in rejected[:12]:
            log(f"[chs]   rejected {en}: model said {ans!r}")

    return terms


if __name__ == "__main__":
    vid = sys.argv[1]
    from common import job_dir
    meta = json.loads((job_dir(vid) / "meta.json").read_text(encoding="utf-8"))
    terms = resolve(meta.get("description") or "",
                    force="--force" in sys.argv)
    for en, zh in sorted(terms.items()):
        print(f"  {en:<34} -> {zh}")
    print(f"\n{len(terms)} resolved")


def deck_text(video_id):
    """Decklist source for a job: the description, or a manually transcribed
    <job>/decklist.txt when the video only shows its deck on screen."""
    from common import job_dir
    d = job_dir(video_id)
    meta_p = d / "meta.json"
    desc = ""
    if meta_p.exists():
        try:
            desc = json.loads(meta_p.read_text(encoding="utf-8")).get("description") or ""
        except Exception:
            desc = ""
    if chs.deck_lines(desc):
        return desc
    p = d / "decklist.txt"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return desc


def deck_overrides(video_id):
    """Per-job EN -> CN name sheet for cards the CN set hasn't printed yet
    (or whose official CN name differs from the dataset's guess).

    Kept in <job>/deck_zh.json so an unreleased set can still get consistent
    names across the whole subtitle.
    """
    from common import job_dir
    p = job_dir(video_id) / "deck_zh.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            log(f"[chs] deck_zh.json unreadable: {e}")
    return {}


def resolve_for(video_id, force=False):
    """Verified CN names for this job's deck, with per-job overrides on top."""
    terms = resolve(deck_text(video_id), force=force)
    terms.update(deck_overrides(video_id))
    return terms
