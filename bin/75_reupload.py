#!/usr/bin/env python3
"""Re-upload helper: shows the old submission(s) then uploads the fixed version.

Bilibili's delete endpoint requires a captcha, so this script cannot remove the
old entry. It prints clickable links so the old submission can be deleted in
the creator centre, then performs a clean upload with the corrected metadata.
"""
import asyncio, json, subprocess, sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))
from common import log

OLD_AID = 117621001296511
OLD_BVID = "BV1KNss6VEyd"


def show_old():
    log("=" * 60)
    log("需要你手动删除旧稿件（B 站删除接口要图形验证码，脚本做不了）：")
    log(f"  BV 号: {OLD_BVID}")
    log(f"  aid:   {OLD_AID}")
    log("  创作中心 → 稿件管理 → 找到该稿件 → 更多 → 删除")
    log("  https://member.bilibili.com/platform/upload-manager/article")
    log("=" * 60)


if __name__ == "__main__":
    vid = sys.argv[1]
    show_old()
    log("\n现在上传修正版（版权=转载 + 标题带【搬运】【自用】）…\n")
    rc = subprocess.run([sys.executable, str(BIN / "70_upload.py"), vid]).returncode
    raise SystemExit(rc)
