#!/usr/bin/env python3
"""Switch the translation model between the Alma cloud provider and local Ollama.

  python bin/use_local.py            # show current backend + whether Ollama is up
  python bin/use_local.py local      # translate with local Ollama
  python bin/use_local.py cloud      # translate with the Alma provider
"""
import json, sys, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CONFIG, model_backend, log

P = CONFIG / "settings.json"


def save(mode):
    s = json.loads(P.read_text(encoding="utf-8"))
    s.setdefault("provider", {})["mode"] = mode
    P.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


def ollama_tags(base):
    try:
        with urllib.request.urlopen(base + "/api/tags", timeout=5) as r:
            d = json.load(r)
        return [m["name"] for m in d.get("models", [])]
    except Exception as e:
        return f"unreachable ({e})"


def main():
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
        if mode not in ("local", "cloud"):
            raise SystemExit("usage: use_local.py [local|cloud]")
        save(mode)
    b = model_backend()
    print(f"mode   : {b['mode']}")
    print(f"model  : {b['model']}")
    print(f"base   : {b['base']}")
    if b["mode"] == "local":
        print(f"ollama : {ollama_tags(b['base'])}")


if __name__ == "__main__":
    main()
