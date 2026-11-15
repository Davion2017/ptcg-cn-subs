#!/usr/bin/env python3
"""Update an already-submitted video's title/desc without re-uploading."""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import job_dir, log, ROOT
from bilibili_api import Credential
from bilibili_api.utils.network import Api

COOKIE_FILE = ROOT / "config" / "bili_cookies.json"


def cred():
    c = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
    return Credential(sessdata=c["SESSDATA"], bili_jct=c["bili_jct"],
                      dedeuserid=c["DedeUserID"],
                      ac_time_value=c.get("ac_time_value", ""))


async def update(aid, video_id):
    d = job_dir(video_id)
    meta = json.loads((d / "bili.json").read_text(encoding="utf-8"))
    api = {"url": "https://member.bilibili.com/x/vu/web/edit", "method": "POST",
           "verify": True, "wbi": True,
           "data": {"aid": aid, "title": meta["title"][:80],
                    "desc": meta["desc"][:1900],
                    "tag": ",".join(meta.get("tags", []))[:200]}}
    try:
        r = await Api(credential=cred(), **api).result
        log(f"[update] OK: {json.dumps(r, ensure_ascii=False)[:200]}")
    except Exception as e:
        log(f"[update] 失败 {type(e).__name__}: {str(e)[:200]}")
        log("        （B 站编辑接口通常需要 csrf 或验证码，也可去创作中心手动改）")


if __name__ == "__main__":
    asyncio.run(update(int(sys.argv[1]), sys.argv[2]))
