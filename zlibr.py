#!/usr/bin/env python3
"""Z-Library 助手（eAPI 直连，免费账号可用）。

用法:
  .venv/bin/python zlibr.py search <书名/ISBN>
  .venv/bin/python zlibr.py download <书名> [--format epub]

凭据: 从 ~/.env 读取 USERNAME / PASSWORD / SITE（z-library.im）
流程: eAPI 登录 -> 搜索 -> 详情(含 download_location) -> 过 PoW 挑战 -> 取文件
"""
import asyncio
import hashlib
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

import aiohttp

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
ENV_PATH = Path.home() / ".env"


def load_credentials() -> dict:
    email = os.environ.get("ZLIB_EMAIL")
    password = os.environ.get("ZLIB_PASSWORD")
    if email and password:
        return {
            "email": email,
            "password": password,
            "site": "https://" + os.environ.get("ZLIB_SITE", "z-library.im").lstrip("https://"),
        }
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    if "USERNAME" not in env or "PASSWORD" not in env:
        sys.exit("请先按需加载账号: source ~/.env && zlib-2（或 ZLIB_EMAIL/ZLIB_PASSWORD 环境变量）")
    return {
        "email": env["USERNAME"],
        "password": env["PASSWORD"],
        "site": "https://" + env.get("SITE", "z-library.im").lstrip("https://"),
    }


def solve_pow(prefix: str, n1: int) -> str:
    i = 0
    while True:
        d = hashlib.sha1((prefix + str(i)).encode()).digest()
        if d[n1] == 0xB0 and d[n1 + 1] == 0x0B:
            return prefix + str(i)
        i += 1


def parse_challenge(body: bytes):
    m = re.search(rb"a0_0x2a54=\['([0-9A-Fa-f]{40})'", body)
    if not m:
        raise RuntimeError("无法解析 PoW 挑战（页面结构可能已变）")
    prefix = m.group(1).decode()
    return prefix, int(prefix[0], 16)


class Zlibr:
    def __init__(self, cred: dict):
        self.site = cred["site"]
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": UA}, cookie_jar=aiohttp.CookieJar(unsafe=True)
        )
        self.cred = cred

    async def close(self):
        await self.session.close()

    async def _req(self, method: str, path: str, tries: int = 6, **kw):
        last = None
        for i in range(tries):
            try:
                async with self.session.request(method, self.site + path, **kw) as r:
                    return await r.read(), r.status, r.headers.get("content-type", "")
            except Exception as e:
                last = e
                await asyncio.sleep(5 + i * 5)
        raise last

    async def login(self):
        body, status, _ = await self._req("POST", "/eapi/user/login",
                                          data={"email": self.cred["email"], "password": self.cred["password"]})
        if status != 200:
            raise RuntimeError(f"登录失败 HTTP {status}")
        data = json.loads(body)
        if data.get("success") != 1:
            raise RuntimeError(f"登录失败: {data.get('error')}")

    async def search(self, query: str, limit: int = 10) -> list:
        body, status, _ = await self._req("POST", "/eapi/book/search",
                                          data={"message": query, "limit": str(limit)})
        data = json.loads(body)
        return data.get("books", [])

    async def details(self, book: dict) -> dict:
        body, status, _ = await self._req("GET", f"/eapi/book/{book['id']}/{book['hash']}")
        data = json.loads(body)
        return data.get("book", {})

    async def download_file(self, download_location: str, out: Path):
        dl = urllib.parse.unquote(download_location)
        path = dl.replace(self.site, "")
        body, status, ctype = await self._req("GET", path)
        if status == 503 and b"Checking your browser" in body:
            prefix, n1 = parse_challenge(body)
            token = solve_pow(prefix, n1)
            self.session.cookie_jar.update_cookies({"c_token": token, "c_time": "0.100"})
            body, status, ctype = await self._req("GET", path)
        if status != 200:
            raise RuntimeError(f"下载失败 HTTP {status}")
        out.write_bytes(body)
        return ctype, len(body)


async def cmd_search(query: str):
    cred = load_credentials()
    z = Zlibr(cred)
    try:
        await z.login()
        books = await z.search(query)
        if not books:
            print("未找到结果")
            return
        for b in books:
            print(f"  [{b.get('extension','?')}] {b.get('title','?')} | {b.get('author','?')} "
                  f"| {b.get('year','?')} | {b.get('filesizeString','?')} | id={b.get('id')}")
    finally:
        await z.close()


async def cmd_download(query: str, ext: str):
    cred = load_credentials()
    z = Zlibr(cred)
    try:
        await z.login()
        books = await z.search(query)
        if not books:
            print("未找到结果")
            return
        matches = [b for b in books if b.get("extension") == ext] or books
        book = matches[0]
        print(f"解析详情: {book.get('title')} ({book.get('extension')})")
        det = await z.details(book)
        ru = det.get("readOnlineUrl")
        if not ru or "download_location=" not in ru:
            print("详情中没有下载地址")
            return
        dl = ru.split("download_location=")[1].split("&")[0]
        safe = "".join(c for c in book.get("title", "book") if c not in '\\/:*?"<>|').strip()[:60]
        out = Path("books") / f"{safe}.{ext}"
        ctype, size = await z.download_file(dl, out)
        print(f"已保存: {out} ({size} bytes, {ctype})")
    finally:
        await z.close()


async def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, arg = sys.argv[1], sys.argv[2]
    if cmd == "search":
        await cmd_search(arg)
    elif cmd == "download":
        ext = "epub"
        if len(sys.argv) > 3 and sys.argv[3] == "--format":
            ext = sys.argv[4]
        await cmd_download(arg, ext)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    asyncio.run(main())