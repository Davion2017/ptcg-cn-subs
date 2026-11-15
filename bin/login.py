#!/usr/bin/env python3
"""One-time Bilibili login via TV QR flow (returns real cookie values)."""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, log

from bilibili_api import login_v2

COOKIE_FILE = ROOT / "config" / "bili_cookies.json"


async def main():
    qr = login_v2.QrCodeLogin(platform=login_v2.QrCodeLoginChannel.TV)
    await qr.generate_qrcode()
    png = ROOT / "config" / "bili_qrcode.png"
    png.write_bytes(qr.get_qrcode_picture().content)
    log(f"[login] 二维码已保存: {png}")
    log("[login] 用 B 站 App 扫码（TV 端登录，扫码后需要在手机上确认）")

    while True:
        state = await qr.check_state()
        if state == login_v2.QrCodeLoginEvents.DONE:
            cred = qr.get_credential()
            cookies = cred.get_cookies()
            filled = {k: v for k, v in cookies.items() if v}
            if not filled.get("SESSDATA") and not filled.get("sessdata"):
                log(f"[login] 警告：返回的 cookie 为空 {list(cookies)}")
                return
            COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
            log(f"[login] 成功，保存 {len(filled)} 项: {sorted(filled)}")
            return
        if state == login_v2.QrCodeLoginEvents.TIMEOUT:
            log("[login] 二维码过期，重跑本脚本")
            return
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
