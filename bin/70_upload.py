#!/usr/bin/env python3
"""Stage 7: upload a finished video to Bilibili.

Uses bilibili-api-python with the cookies saved by bin/login.py.
Never fabricates success: it reports the real aid/bvid or raises.
"""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import job_dir, log, ROOT

COOKIE_FILE = ROOT / "config" / "bili_cookies.json"

# 分区 tid: 27=单机游戏 17=单机游戏→其他 138=搞笑 21=日常
DEFAULT_TID = 27

# 每条稿件标题必须以这两个标记开头
TITLE_PREFIX = "【搬运】【自用】"


def ensure_title_prefix(title):
    """Guarantee the reprint/self-use markers lead the title exactly once."""
    t = (title or "").strip()
    for tag in ("【搬运】", "【自用】"):
        if t.startswith(tag):
            t = t[len(tag):].lstrip()
    return TITLE_PREFIX + t


def build_credential():
    from bilibili_api import Credential
    if not COOKIE_FILE.exists():
        raise SystemExit("未登录：先运行 python bin/login.py")
    c = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
    sess = c.get("SESSDATA") or c.get("sessdata")
    if not sess:
        raise SystemExit("cookie 里没有 SESSDATA，重新运行 python bin/login.py")
    return Credential(
        sessdata=sess,
        bili_jct=c.get("bili_jct", ""),
        buvid3=c.get("buvid3", ""),
        buvid4=c.get("buvid4", ""),
        dedeuserid=c.get("DedeUserID") or c.get("dedeuserid", ""),
        ac_time_value=c.get("ac_time_value", ""),
    )


async def do_upload(video_id, tid=DEFAULT_TID, dry_run=False):
    from bilibili_api import video_uploader
    d = job_dir(video_id)
    video = d / "final.mp4"
    meta_p = d / "bili.json"
    if not video.exists():
        raise SystemExit("没有 final.mp4，先跑 50_render.py")
    if not meta_p.exists():
        raise SystemExit("没有 bili.json，先跑 60_meta.py")

    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    meta["title"] = ensure_title_prefix(meta.get("title", ""))
    desc = (meta.get("desc") or "").replace("{{URL}}", meta.get("source_url", ""))
    cover = d / "cover.jpg" if (d / "cover.jpg").exists() else d / "cover_raw.jpg"

    log(f"[upload] 标题: {meta.get('title')}")
    body = meta['title'][len(TITLE_PREFIX):]
    if len(meta['title']) > 80:
        raise SystemExit(f"标题超长（{len(meta['title'])} 字符），请缩短")
    log(f"[upload] 分区 tid={tid} 标签: {', '.join(meta.get('tags', []))}")
    log(f"[upload] 转载来源: {meta.get('source_url')}")

    if dry_run:
        log("[upload] dry-run，不实际提交")
        return None

    credential = build_credential()
    page = video_uploader.VideoUploaderPage(
        path=str(video),
        title=meta.get("title", "")[:80],
        description=desc[:1900],
    )
    uploader = video_uploader.VideoUploader(
        pages=[page],
        meta=video_uploader.VideoMeta(
            tid=tid,
            title=meta.get("title", "")[:80],
            desc=desc[:1900],
            tags=meta.get("tags", [])[:10],
            cover=str(cover) if cover.exists() else "",
            no_reprint=False,            # False = 允许转载
            original=False,              # False = 转载（copyright=2）
            source=meta.get("source_url", ""),
        ),
        credential=credential,
    )

    @uploader.on("__ALL__")
    async def _ev(data):
        log(f"[upload] {data.get('name')}: {data.get('data')}")

    result = await uploader.start()
    log(f"[upload] 完成: {json.dumps(result, ensure_ascii=False)}")
    (d / "upload_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tid = DEFAULT_TID
    for a in sys.argv[1:]:
        if a.startswith("--tid="):
            tid = int(a.split("=")[1])
    asyncio.run(do_upload(args[0], tid=tid, dry_run="--dry-run" in sys.argv))
