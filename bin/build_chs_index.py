#!/usr/bin/env python3
"""Build an official Simplified-Chinese card-name index.

Sources
  - data/chs/ptcg_chs_infos.json : official CN card / move / ability names
                                   (duanxr/PTCG-CHS-Datasets), with pokedexCode
  - api.tcgdex.net               : English card names by set + localId, plus
                                   dexId per card, so EN names can be tied to
                                   the CN dex number.

Output: data/chs/chs_index.json
  {
    "dex": {"605": {"en": "Elgyem", "zh": "小灰怪"}, ...},
    "en_to_zh": {"Elgyem": "小灰怪", ...},          # pokemon only, dex-derived
    "cn_cards": [...], "cn_moves": [...],           # official pool
    "sets": {"sv10.5b": {"001": "Snivy", ...}}
  }
"""
import json, sys, urllib.request, concurrent.futures
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHS = ROOT / "data" / "chs"
OUT = CHS / "chs_index.json"

# Simplified-Chinese Standard format is G-onwards (亘古开来 was the first G-mark
# set; A-F have rotated out). Keeping only legal marks halves the name pool the
# model has to pick from and stops it choosing an old-format name variant.
LEGAL_MARKS = {"G", "H", "I", "J"}

# English set code used in decklists -> tcgdex set id
SETMAP = {
    "SVI": "sv01", "PAL": "sv02", "OBF": "sv03", "MEW": "sv03.5",
    "PAR": "sv04", "PAF": "sv04.5", "TEF": "sv05", "TWM": "sv06",
    "SFA": "sv06.5", "SCR": "sv07", "SSP": "sv08", "PRE": "sv08.5",
    "JTG": "sv09", "DRI": "sv10", "BLK": "sv10.5b", "WHT": "sv10.5w",
}


def get(url, timeout=60, retries=3):
    import time
    last = None
    for _ in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            last = e
            time.sleep(1.5)
    raise RuntimeError(f"{url}: {last}")


def load_cn():
    d = json.loads((CHS / "ptcg_chs_infos.json").read_text(encoding="utf-8"))
    cards, moves, dex = set(), set(), {}
    set_cn, dex_cands = {}, {}
    for coll in d["collections"]:
        for k in coll.get("cards", []):
            name = (k.get("name") or "").strip()
            det = k.get("details") or {}
            if det.get("regulationMarkText") not in LEGAL_MARKS:
                continue
            if name:
                cards.add(name)
            if det.get("cardTypeText") == "宝可梦":
                code = det.get("pokedexCode")
                if code and name:
                    try:
                        dex.setdefault(str(int(code)), set()).add(name)
                    except ValueError:
                        pass
            for a in det.get("abilityItemList") or []:
                n = (a.get("abilityName") or "").strip()
                if n and n != "none":
                    moves.add(n)
            code = k.get("commodityCode") or coll.get("commodityCode")
            if code and name:
                set_cn.setdefault(code, []).append(name)
            if str(det.get("pokedexCode") or "").isdigit() and name:
                dex_cands.setdefault(str(int(det["pokedexCode"])), set()).add(name)
            for f in det.get("cardFeatureItemList") or []:
                n = (f.get("featureName") or "").strip()
                if n and n != "none":
                    moves.add(n)
    return cards, moves, dex, set_cn, dex_cands


def fetch_set_cards(sid):
    """[(localId, en_name, dexId|None)] for one set."""
    listing = get(f"https://api.tcgdex.net/v2/en/sets/{sid}")
    items = [(c["localId"], c["name"]) for c in listing.get("cards", [])
             if c.get("localId") and c.get("name")]

    def detail(it):
        local, name = it
        try:
            d = get(f"https://api.tcgdex.net/v2/en/cards/{sid}-{local}", timeout=30)
            dex = d.get("dexId") or []
            return local, name, (str(dex[0]) if dex else None)
        except Exception:
            return local, name, None

    out = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(detail, items):
            out.append(r)
    return out


def main(only=None):
    cn_cards, cn_moves, cn_dex, set_cn, dex_cands = load_cn()
    print(f"CN pool: {len(cn_cards)} cards, {len(cn_moves)} moves, {len(cn_dex)} dex", flush=True)

    sets, en_to_zh, dex_map, set_cn_prev, dex_cands_prev = {}, {}, {}, {}, {}
    set_dex = {}
    if only and OUT.exists():
        prev = json.loads(OUT.read_text(encoding="utf-8"))
        sets = prev.get("sets", {})
        en_to_zh = prev.get("en_to_zh", {})
        dex_map = prev.get("dex", {})
        set_cn_prev = prev.get("set_cn", {})
        set_dex = prev.get("set_dex", {})
        dex_cands_prev = prev.get("dex_candidates", {})
        print(f"merging into existing index ({len(en_to_zh)} names)", flush=True)
    codes = only or list(SETMAP)
    for code in codes:
        sid = SETMAP[code]
        try:
            rows = fetch_set_cards(sid)
        except Exception as e:
            print(f"  {code} ({sid}) failed: {e}", flush=True)
            continue
        sets[sid] = {local: name for local, name, _ in rows}
        set_dex[sid] = [d for _, _, d in rows if d]
        hit = 0
        for local, name, dex in rows:
            if not dex:
                continue
            zh_names = cn_dex.get(dex)
            if not zh_names:
                continue
            # prefer the shortest name (plain species, not "N's X" / "X ex")
            zh = sorted(zh_names, key=lambda s: (len(s), s))[0]
            dex_map[dex] = {"en": name, "zh": zh}
            en_to_zh[name] = zh
            hit += 1
        print(f"  {code} ({sid}): {len(rows)} cards, {hit} dex-matched", flush=True)

    for k, v in set_cn.items():
        set_cn_prev[k] = v
    for k, v in dex_cands.items():
        dex_cands_prev.setdefault(k, [])
        dex_cands_prev[k] = sorted(set(dex_cands_prev[k]) | set(v))
    data = {
        "dex": dex_map,
        "en_to_zh": en_to_zh,
        "cn_cards": sorted(cn_cards),
        "cn_moves": sorted(cn_moves),
        "sets": sets,
        "set_dex": set_dex,
        "set_cn": set_cn_prev,
        "dex_candidates": dex_cands_prev,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size/1024:.0f} KB), en_to_zh={len(en_to_zh)}")


if __name__ == "__main__":
    main([a for a in sys.argv[1:] if not a.startswith("-")] or None)
