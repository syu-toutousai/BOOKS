# BOOKS — 实体书数字分身

个人藏书目录：实体书档案（书目信息 + 数字分身）。电子书本体不入库，仅保留来源页链接。

## 项目结构

```
BOOKS/
├── catalog.json   # 图书馆索引（机器可读，含 ebook_url）
├── books/         # 单书档案 *.md（书名/作者/出版社/ISBN/定价 + 数字分身）
├── zlibr.py       # Z-Library 电子版查询/下载助手
├── index.md       # Pages 首页（从 catalog.json 生成）
└── .gitignore     # 排除 *.epub/*.pdf 等电子书实体
```

## 工作流

1. 提供 ISBN → 查书目信息 → 建档 `books/<ISBN>.md` + 登记 `catalog.json`（status 默认"未读"）
2. 可选：用 `zlibr.py` 查/下电子版，档案中记录来源 URL；无对应版本则注明
3. 电子书实体文件一律 gitignore，公开仓库中仅暴露绝对 URL 链接

## zlibr.py 用法

凭据存于 `~/.env`（项目外，`chmod 600`），按需 source：

```bash
source ~/.env && zlib-2   # 激活账号，导出 ZLIB_EMAIL/PASSWORD/SITE
.venv/bin/python zlibr.py search <书名>
.venv/bin/python zlibr.py download <书名> --format epub
```

- z-library eAPI 直连（form 登录 → 搜索 → 详情 → download_location），需过 SHA-1 工作量证明反爬
- 仅支持书名/作者搜索（ISBN 搜不到）；免费账号有登录频率限制与每日下载额度
- 依赖仅 `aiohttp`（`.venv/`）

## 站点

- GitHub Pages: https://syu-toutousai.github.io/BOOKS/