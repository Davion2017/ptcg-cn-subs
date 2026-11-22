"""Shared helpers: config, provider credentials, paths, logging."""
import json, os, re, subprocess, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"
WORK = ROOT / "work"


def load_settings():
    return json.loads((CONFIG / "settings.json").read_text(encoding="utf-8"))


def model_backend():
    """Describe how to reach the translation model.

    settings.provider.mode:
      "cloud" (default) -> the Alma app's provider, OpenAI-compatible endpoint
      "local"           -> an Ollama server, /api/chat, thinking disabled
    """
    s = load_settings()
    prov = s.get("provider", {})
    mode = (prov.get("mode") or "cloud").lower()
    if mode == "local":
        loc = prov.get("local") or {}
        return {
            "mode": "local",
            "base": (loc.get("base") or "http://localhost:11434").rstrip("/"),
            "model": loc.get("model") or "qwen3.5:9b",
            "key": "",
            "num_ctx": loc.get("num_ctx") or 32768,
        }
    base, key = provider_credentials()
    return {"mode": "cloud", "base": base, "model": prov["model"], "key": key}


def provider_credentials():
    """Read provider endpoint/key from the running Alma app."""
    with urllib.request.urlopen("http://localhost:23001/api/providers", timeout=20) as r:
        payload = json.load(r)
    provs = payload if isinstance(payload, list) else payload.get("providers", [])
    if not provs:
        raise RuntimeError("no provider configured in Alma")
    p = provs[0]
    return p["baseURL"].rstrip("/"), p["apiKey"]


def log(msg):
    print(msg, flush=True)


def resolve(name):
    """Resolve a tool name, preferring the project venv and Homebrew."""
    local = Path(sys.executable).parent / name
    if local.exists():
        return str(local)
    for prefix in ("/opt/homebrew/bin", "/usr/local/bin"):
        cand = Path(prefix) / name
        if cand.exists():
            return str(cand)
    return name


def run(cmd, **kw):
    """Run a command, returning (rc, out, err). First arg may be a bare tool name."""
    cmd = list(cmd)
    cmd[0] = resolve(cmd[0])
    p = subprocess.run(cmd, capture_output=True, text=True, **kw)
    return p.returncode, p.stdout, p.stderr


def slug(text, limit=60):
    text = re.sub(r"[^\w\u4e00-\u9fff\- ]+", "", text).strip()
    text = re.sub(r"\s+", "-", text)
    return text[:limit].strip("-") or "untitled"


def fmt_srt_time(seconds):
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def parse_srt_time(stamp):
    stamp = stamp.strip().replace(",", ".")
    h, m, s = stamp.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def read_srt(path):
    """Parse an SRT file into [{index,start,end,text}]."""
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"\r?\n\r?\n", raw.strip())
    cues = []
    for b in blocks:
        lines = [l for l in b.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        idx = None
        m = re.fullmatch(r"\d+", lines[0].strip())
        if m:
            idx = int(lines[0].strip())
            lines = lines[1:]
        if not lines:
            continue
        tm = re.search(r"(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})", lines[0])
        if not tm:
            continue
        cues.append({
            "index": idx if idx is not None else len(cues) + 1,
            "start": parse_srt_time(tm.group(1)),
            "end": parse_srt_time(tm.group(2)),
            "text": "\n".join(lines[1:]).strip(),
        })
    return cues


def write_srt(cues, path):
    out = []
    for i, c in enumerate(cues, 1):
        out.append(str(i))
        out.append(f"{fmt_srt_time(c['start'])} --> {fmt_srt_time(c['end'])}")
        out.append(c["text"])
        out.append("")
    Path(path).write_text("\n".join(out), encoding="utf-8")


def job_dir(video_id):
    d = DATA / "jobs" / video_id
    d.mkdir(parents=True, exist_ok=True)
    return d
