"""Glossary lookup with fuzzy matching for ASR-mangled card names."""
import json, re, difflib
from pathlib import Path

from common import CONFIG

_cache = {}

_APOS = {"\u2019": "'", "\u2018": "'", "\u00b4": "'", "\u02bc": "'"}


def norm(text):
    """Normalise typographic apostrophes so lookups don't silently miss."""
    for bad, good in _APOS.items():
        text = text.replace(bad, good)
    return text


def load():
    if "g" not in _cache:
        p = CONFIG / "glossary.json"
        raw = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        _cache["g"] = {norm(k): v for k, v in raw.items() if not k.startswith("_")}
    return _cache["g"]


def load_aliases():
    """ASR-mangled English name -> canonical English name."""
    if "a" not in _cache:
        p = CONFIG / "aliases.json"
        raw = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        _cache["a"] = {norm(k): v for k, v in raw.items() if not k.startswith("_")}
    return _cache["a"]


def apply_aliases(text):
    """Rewrite known mis-hearings to the canonical English name."""
    aliases = load_aliases()
    for wrong, right in sorted(aliases.items(), key=lambda x: -len(x[0])):
        if wrong == right:
            continue
        text = re.sub(r"\b" + re.escape(wrong) + r"\b", right, text)
    return text


def _keys():
    if "k" not in _cache:
        _cache["k"] = sorted(load().keys(), key=len, reverse=True)
    return _cache["k"]


def exact_terms(text):
    """Return glossary terms literally present in text (longest first)."""
    text = apply_aliases(norm(text))
    found = []
    low = text.lower()
    for k in _keys():
        if len(k) < 4:
            continue
        if k.lower() in low:
            found.append(k)
    return found


def fuzzy_terms(text, cutoff=0.78):
    """Catch ASR-mangled card names: capitalised words/likely proper nouns."""
    text = apply_aliases(norm(text))
    g = load()
    out = []
    # candidate tokens: capitalised words, or short multiword phrases
    cands = re.findall(r"\b[A-Z][a-zA-Z'’\-]{3,}\b", text)
    cands += re.findall(r"\b[A-Z][a-zA-Z'’\-]+(?:\s+[A-Z][a-zA-Z'’\-]+)*\s+(?:EX|ex|GX|V)\b", text)
    keys = _keys()
    for c in set(cands):
        if c in g:
            continue
        m = difflib.get_close_matches(c, keys, n=1, cutoff=cutoff)
        if m:
            out.append((c, m[0], g[m[0]]))
    return out


def build_prompt_block(limit=60):
    g = load()
    if not g:
        return ""
    # keep the prompt small: only the most likely relevant entries
    priority = [k for k in g if len(k) > 5][:limit]
    return "\n".join(f"{k} = {g[k]}" for k in priority)


def resolve_report(text):
    """For diagnostics: what does the glossary say about this text."""
    lines = []
    for t in exact_terms(text):
        lines.append(f"exact  {t} = {load()[t]}")
    for c, m, zh in fuzzy_terms(text):
        lines.append(f"fuzzy  {c} ≈ {m} = {zh}")
    return lines
