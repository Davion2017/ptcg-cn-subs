"""Official Simplified-Chinese card names (Pokémon Shanghai naming).

Index: data/chs/chs_index.json, built by bin/build_chs_index.py from
  - duanxr/PTCG-CHS-Datasets  official CN card / move names, pokedexCode, type
  - api.tcgdex.net            English names + dexId per set/localId

The hand-maintained glossary only covered ~1/3 of the official pool, so
subtitles kept drifting to fan translations. Here we resolve the *deck list*
of the video (English name + set code + collector number) to official CN
names, and use those as authoritative terms during translation, then verify
the finished subtitle against them.
"""
import json, re, difflib
from common import DATA

INDEX = DATA / "chs" / "chs_index.json"

SETMAP = {
    "SVI": "sv01", "PAL": "sv02", "OBF": "sv03", "MEW": "sv03.5",
    "PAR": "sv04", "PAF": "sv04.5", "TEF": "sv05", "TWM": "sv06",
    "SFA": "sv06.5", "SCR": "sv07", "SSP": "sv08", "PRE": "sv08.5",
    "JTG": "sv09", "DRI": "sv10", "BLK": "sv10.5b", "WHT": "sv10.5w",
}

# English form / owner words -> the Chinese wording the CN printing uses
QUALIFIERS = [
    ("Cornerstone Mask", "础石面具"), ("Wellspring Mask", "水井面具"),
    ("Hearthflame Mask", "火灶面具"), ("Teal Mask", "碧草面具"),
]
OWNERS = {
    "N's": "N的", "Ethan's": "阿响的", "Team Rocket's": "火箭队的",
    "Lillie's": "莉莉艾的", "Marnie's": "玛俐的", "Erika's": "莉佳的",
    "Brock's": "小刚的", "Misty's": "小霞的", "Arven's": "派帕的",
    "Mela's": "梅洛可的", "Atticus's": "皮拿的", "Giacomo's": "梅洛可的",
    "Larry's": "青木的", "Cynthia's": "竹兰的", "Cilan's": "天桐的",
    "Iris's": "艾莉丝的", "Hop's": "赫普的", "Bede's": "彼特的",
    "Marnie's": "玛俐的", "Raihan's": "奇巴纳的", "Sonia's": "索妮亚的",
    "Roark's": "瓢太的", "Volkner's": "电次的", "Fantina's": "梅丽莎的",
}
# Rotom appliances: Fan Rotom -> 风扇洛托姆
ROTOM = {
    "Fan Rotom": "风扇洛托姆", "Heat Rotom": "加热洛托姆",
    "Wash Rotom": "清洗洛托姆", "Frost Rotom": "结冰洛托姆",
    "Mow Rotom": "割草洛托姆",
}

_cache = {}


def load():
    if "i" not in _cache:
        _cache["i"] = (json.loads(INDEX.read_text(encoding="utf-8"))
                       if INDEX.exists() else {})
    else:
        return _cache["i"]
    idx = _cache["i"]
    idx.setdefault("sets", {}); idx.setdefault("en_to_zh", {})
    idx.setdefault("cn_cards", []); idx.setdefault("cn_moves", [])
    idx.setdefault("dex", {}); idx.setdefault("set_cn", {})
    # Every CN printing of a species shares its dex entry, but ex cards in the
    # dataset carry no pokedexCode, so extend the candidate list from set_cn.
    allnames = set()
    for names in idx.get("set_cn", {}).values():
        allnames.update(names)
    allnames.update(idx.get("cn_cards", []))
    cands = idx.setdefault("dex_candidates", {})
    for dex, lst in list(cands.items()):
        base = min(lst, key=len)
        stem = base[:-2] if base.endswith("ex") else base
        if not stem:
            continue
        for n in allnames:
            if n != stem and n.startswith(stem) and n not in lst:
                lst.append(n)
    # lowercase EN name -> dex, tolerant of a missing/bogus "ex" suffix
    en2dex = {}
    for d, rec in idx.get("dex", {}).items():
        en = (rec.get("en") or "").strip().lower()
        if not en:
            continue
        en2dex.setdefault(en, d)
        base = re.sub(r"\s+ex$", "", en)
        en2dex.setdefault(base, d)
        en2dex.setdefault(base + " ex", d)
    idx["_en2dex"] = en2dex
    # dex -> {name: type text}
    if "dex_names" not in idx:
        idx["dex_names"] = {k: v for k, v in idx.get("dex", {}).items()}
    return idx


def available():
    return INDEX.exists()


def deck_lines(description):
    """Parse `4 Dudunsparce TEF 129` style lines out of a video description."""
    out = []
    for line in (description or "").splitlines():
        m = re.match(r"^\s*(\d+)\s+(.+?)\s+([A-Z]{2,4})\s+(\d{1,3})\s*$", line)
        if m:
            out.append({"count": int(m.group(1)), "en": m.group(2).strip(),
                        "code": m.group(3), "num": m.group(4)})
    return out


def _score(en, cn):
    """How well a CN candidate name corresponds to the English name."""
    s = 0
    low = en.lower()
    is_ex = bool(re.search(r"\bex\b", low))
    cn_ex = cn.endswith("ex")
    if is_ex == cn_ex:
        s += 3
    elif is_ex and not cn_ex:
        s -= 3
    for eng, zh in QUALIFIERS:
        if eng.lower() in low:
            s += 4 if zh in cn else -3
    for eng, zh in OWNERS.items():
        if low.startswith(eng.lower() + " "):
            s += 4 if zh in cn else -3
    if "Rotom" in en and cn.endswith("洛托姆"):
        s += 2
    # shorter is more likely the plain species printing
    s -= len(cn) * 0.02
    return s


def official_name(en, code, num, idx=None):
    """Best official CN name for one decklist entry, or None."""
    idx = idx or load()
    if en in ROTOM:
        return ROTOM[en]
    sid = SETMAP.get(code)
    has_qualifier = any(q.lower() in en.lower() for q, _ in QUALIFIERS)
    has_owner = any(en.lower().startswith(o.lower() + " ") for o in OWNERS)
    # 1) exact printing: same name at the same set+number
    cards = idx.get("sets", {}).get(sid or "", {})
    local = str(num).zfill(3)
    if not (has_qualifier or has_owner):
        if cards.get(local) and cards[local].lower() == en.lower():
            # The printing matches, but en_to_zh came from the shortest name
            # of the species, which loses the "ex" suffix. Re-score candidates.
            dex0 = idx.get("_en2dex", {}).get(en.strip().lower())
            cands0 = idx.get("dex_candidates", {}).get(dex0 or "", [])
            if cands0:
                return max(cands0, key=lambda c: _score(en, c))
            zh = idx.get("en_to_zh", {}).get(en)
            if zh:
                return zh
    # 2) dex candidates, scored
    dex = idx.get("_en2dex", {}).get(en.strip().lower())
    cands = idx.get("dex_candidates", {}).get(dex or "", [])
    if cands:
        best = max(cands, key=lambda c: _score(en, c))
        # Masks (Ogerpon) and owner prefixes sometimes have no matching
        # printing in the dataset; assemble 「species + qualifier + ex」.
        want = None
        for eng, zh in QUALIFIERS:
            if eng.lower() in en.lower():
                want = zh
        if want and want not in best:
            species = min(cands, key=len).replace("ex", "").strip()
            is_ex = bool(re.search(r"\bex\b", en.lower()))
            return species + " " + want + ("ex" if is_ex else "")
        return best
    # 3) name map built from dex matching
    return idx.get("en_to_zh", {}).get(en)


def deck_terms(description, idx=None):
    """EN card name -> official CN name for every card in this decklist."""
    idx = idx or load()
    terms = {}
    for d in deck_lines(description):
        zh = official_name(d["en"], d["code"], d["num"], idx)
        if zh and zh != d["en"]:
            terms[d["en"]] = zh
    return terms


def near_miss(text, official, max_diff=None):
    """Fan-translated variants of official names inside running text.

    A window of the same length is accepted only when its first and last
    characters match and at most 1-2 interior characters differ, which is how
    fan translations drift (保母曼波/保姆曼波, 厄鬼椪/厄诡椪) but rejects shifted
    windows that merely look similar to difflib.
    """
    official = sorted({o for o in official if o and len(o) >= 3},
                      key=len, reverse=True)
    if not official:
        return []
    runs = re.findall(r"[\u4e00-\u9fff]{3,}", text)
    fixes = set()
    for run in runs:
        for off in official:
            n = len(off)
            if n > len(run):
                continue
            allowed = max_diff if max_diff is not None else (1 if n <= 5 else 2)
            for i in range(0, len(run) - n + 1):
                win = run[i:i + n]
                if win == off:
                    continue
                if win[0] != off[0] or win[-1] != off[-1]:
                    continue
                diff = sum(1 for a, b in zip(win, off) if a != b)
                if 0 < diff <= allowed:
                    fixes.add((win, off))
    return sorted(fixes, key=lambda x: -len(x[0]))


def english_leftovers(text, en_names):
    """English card names that survived into the Chinese subtitle."""
    out = []
    for en in en_names:
        if len(en) < 4:
            continue
        pat = r"(?<![A-Za-z])" + re.escape(en) + r"(?![A-Za-z])"
        for m in re.finditer(pat, text, re.I):
            before = text[max(0, m.start() - 2):m.start()]
            if before.endswith("(") or before.endswith("（"):
                continue           # 中文名(English) 是允许的写法
            out.append(en)
            break
    return out
