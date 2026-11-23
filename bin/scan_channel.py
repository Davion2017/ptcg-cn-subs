#!/usr/bin/env python3
"""Scan a YouTube channel for videos a Simplified-Chinese audience can use.

A video qualifies when its decklist only uses sets at or before the CN Standard
cutoff (BLK/WHT today). Videos with no decklist in the description can't be
judged automatically and are reported separately as "unknown".

Usage:
  python bin/scan_channel.py @AzulGG
  python bin/scan_channel.py @AzulGG --since 2025-06 --min-views 5000
  python bin/scan_channel.py @ControlPlayersUnite --refresh
"""
import argparse, concurrent.futures, json, re, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, log

CACHE = DATA / "channels"

# Release order of the sets a CN player can still meet, oldest first.
ORDER = ["SVI", "PAL", "TEF", "TWM", "SFA", "SCR", "SSP", "PRE",
         "JTG", "DRI", "BLK", "WHT", "MEG", "PFL", "ASC", "POR", "MEP"]
CUTOFF = "WHT"          # CN Standard currently ends at Black Bolt / White Flare
IDX = {c: i for i, c in enumerate(ORDER)}


def handle_slug(h):
    return re.sub(r"[^A-Za-z0-9_.-]", "", h.lstrip("@")) or "channel"


def list_videos(handle):
    r = subprocess.run(["yt-dlp", "--flat-playlist",
                        "--print", "%(id)s|%(duration)s|%(view_count)s|%(title)s",
                        f"https://www.youtube.com/{handle}/videos"],
                       capture_output=True, text=True)
    out = []
    for line in r.stdout.splitlines():
        p = line.split("|", 3)
        if len(p) == 4:
            out.append({"id": p[0],
                        "duration": int(p[1]) if p[1].isdigit() else 0,
                        "views": int(p[2]) if p[2].isdigit() else 0,
                        "title": p[3]})
    return out


def fetch_meta(ids, workers=10):
    def one(i):
        for _ in range(3):
            try:
                r = subprocess.run(["yt-dlp", "-J", "--no-warnings",
                                    f"https://www.youtube.com/watch?v={i}"],
                                   capture_output=True, text=True, timeout=150)
                j = json.loads(r.stdout)
                return {"id": i, "title": j.get("title"),
                        "upload_date": j.get("upload_date") or "",
                        "duration": j.get("duration") or 0,
                        "views": j.get("view_count") or 0,
                        "description": j.get("description") or ""}
            except Exception:
                pass
        return {"id": i}
    out = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(one, ids):
            out.append(r)
    return out


def deck_range(desc):
    """Latest set code used by the decklist, or None if there is no decklist."""
    cards = re.findall(r"^\s*\d+\s+.+?\s([A-Z]{2,4})\s?\d{1,3}[a-z]?\s*$",
                       desc or "", re.M)
    if not cards:
        return None
    return max(IDX.get(c, -1) for c in cards)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    ap.add_argument("--since", default=None, help="YYYY-MM-DD or YYYY-MM")
    ap.add_argument("--min-views", type=int, default=0)
    ap.add_argument("--limit", type=int, default=400,
                    help="only inspect the newest N uploads (default 400)")
    ap.add_argument("--refresh", action="store_true", help="ignore cache")
    a = ap.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)
    cache_p = CACHE / f"{handle_slug(a.handle)}.json"
    meta = {}
    if cache_p.exists() and not a.refresh:
        meta = {m["id"]: m for m in json.loads(cache_p.read_text(encoding="utf-8"))}
        log(f"cache: {len(meta)} videos")

    listing = list_videos(a.handle)[:a.limit]
    log(f"{a.handle}: {len(listing)} uploads listed")

    missing = [v["id"] for v in listing if v["id"] not in meta]
    if missing:
        log(f"fetching metadata for {len(missing)} new videos…")
        for m in fetch_meta(missing):
            meta[m["id"]] = m
        cache_p.write_text(json.dumps(list(meta.values()), ensure_ascii=False),
                           encoding="utf-8")

    rows, unknown = [], []
    for v in listing:
        m = meta.get(v["id"], {})
        date = m.get("upload_date") or ""
        if a.since:
            want = a.since.replace("-", "")
            if len(want) == 6:
                if date[:6] < want:
                    continue
            elif date < want:
                continue
        views = m.get("views") or v["views"]
        if views < a.min_views:
            continue
        dur = m.get("duration") or v["duration"]
        rng = deck_range(m.get("description"))
        row = {"id": v["id"], "date": date, "duration": dur, "views": views,
               "title": m.get("title") or v["title"]}
        if rng is None:
            unknown.append(row)
        elif rng <= IDX[CUTOFF]:
            rows.append(row)

    rows.sort(key=lambda r: -r["views"])
    print(f"\n可搬（卡表 ≤ {CUTOFF}）: {len(rows)}")
    for r in rows:
        print(f"  {r['date'][:4]}-{r['date'][4:6]}-{r['date'][6:]}  "
              f"{r['duration']//60:>3}min  {r['views']:>7}v  {r['id']}  {r['title'][:62]}")
    print(f"\n描述里没有卡表、需要人工判断: {len(unknown)}")
    for r in unknown[:15]:
        print(f"  {r['date'][:4]}-{r['date'][4:6]}-{r['date'][6:]}  "
              f"{r['duration']//60:>3}min  {r['views']:>7}v  {r['id']}  {r['title'][:62]}")


if __name__ == "__main__":
    main()
