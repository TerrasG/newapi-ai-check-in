#!/usr/bin/env python3
"""
本机弹窗登录 linux.do，捕获 storage state 登录态文件。

用法（本机）：
  .venv\\Scripts\\python.exe tools\\login_linuxdo_gui.py

流程：
  1. 弹出 camoufox 浏览器窗口到 https://linux.do/login
  2. 你在窗口里手动登录（账号密码 / Cloudflare 验证）
  3. 登录成功后回到窗口，按任意键（终端）或等待检测到登录成功
  4. 脚本把登录态（storage state）保存到 storage-states/linuxdo_storage_state.json
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from camoufox.async_api import AsyncCamoufox
from camoufox import DefaultAddons

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "storage-states"
OUT_DIR.mkdir(exist_ok=True)
OUT_FILE = OUT_DIR / "linuxdo_storage_state.json"


async def main() -> int:
    print(f"将保存登录态到: {OUT_FILE}")
    print("弹出浏览器窗口，请手动登录 linux.do ...")
    print("（登录成功后浏览器会停留在页面，按 Ctrl+C 或等待提示）")

    async with AsyncCamoufox(
        headless=False,          # 必须弹窗，让你手动操作
        humanize=True,
        locale="zh-CN",
        os="macos",              # 与签到代码一致，保持指纹稳定
        config={"forceScopeAccess": True},
        exclude_addons=[DefaultAddons.UBO],  # 跳过 UBO 扩展下载，加快启动
    ) as browser:
        context = await browser.new_context()
        page = await context.new_page()

        print("打开 https://linux.do/login ...")
        await page.goto("https://linux.do/login", wait_until="domcontentloaded", timeout=60000)
        print("已打开登录页。请在弹出的浏览器窗口里登录。")

        # 轮询等待登录成功：URL 离开 /login 或页面出现用户标识
        logged_in = False
        for _ in range(60):  # 最多等 10 分钟
            await asyncio.sleep(10)
            try:
                url = page.url
                title = await page.title()
                # 登录成功后 linux.do 会跳转到主站或出现头像
                if "login" not in url and "linux.do" in url:
                    logged_in = True
                    break
                # 也检测页面是否有登录成功标志
                if "登录" in title and "退出" not in title:
                    continue
            except Exception:
                continue

        if not logged_in:
            # 兜底：即使没检测到，也让用户确认
            print("未自动检测到登录成功。如果你已登录，请按回车确认...")
            input()
            logged_in = True

        print("登录成功！保存 storage state ...")
        await context.storage_state(path=str(OUT_FILE))

        data = json.loads(OUT_FILE.read_text(encoding="utf-8"))
        print(f"✅ storage state 已保存: {OUT_FILE}")
        print(f"   cookie 数: {len(data.get('cookies', []))}")
        print(f"   origins: {len(data.get('origins', []))}")
        return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(1)
