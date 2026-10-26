# Kindle 向け AZW3 → MOBI 変換（縦書き・ruby 保持）

更新：2026-10-26
対象：Kindle Paperwhite 第6世代（KF8 対応） / calibre 9.14.0（Linux）
元ファイル：`*.azw3`（KF8）に `<ruby>` と `-webkit-writing-mode: vertical-rl` が入っている日本語書籍

## 0. 結論

- `.mobi` / `.azw` でも、**KF8 を内包した joint（combo）MOBI** なら縦書き・ruby は保持される。
- **KF8 単体**（`--mobi-file-type=new`）を `.mobi` にしたファイルは、Paperwhite では「転送は成功するが開けない」になる。MOBI6 ヘッダ + `BOUNDARY` + KF8 ヘッダを持つ joint にする。
- calibre の基本コマンドは `--mobi-file-type=both`。今回は組版を触らないため、CSS flattener を無効化するラッパーを併用した。
- `.azw3` のまま KF8 対応機に USB 転送するのが最も無損失。`.mobi` / `.azw` が必要な場合の手順が本稿。

## 1. 用語と前提

| 用語 | 意味 |
| --- | --- |
| MOBI6 | 旧 Mobipocket 形式。縦書き・ruby の表現に不向き。 |
| KF8 | Kindle Format 8。AZW3 の中身。縦書き・ruby を扱える。 |
| joint / combo MOBI | 1 ファイルに MOBI6 と KF8 の両方を入れたもの。KF8 対応機は KF8 側を読む。 |
| EXTH 525 | `primary-writing-mode`。`vertical-rl` なら縦書き。 |
| EXTH 527 | `page-progression-direction`。縦書きでは `rtl`。 |

`.azw3` を単に `.mobi` にリネームしても、KF8 単体のままでは Paperwhite の `.mobi` 経路で開けないことがある。拡張子ではなく、joint 構造が重要。

## 2. 元ファイルの確認

```bash
ebook-meta input.azw3 | head -20
```

`Title` / `Author(s)` / `Languages: jpn` などを確認する。次に MOBI ヘッダと EXTH を確認する。

```python
# check_mobi.py
import struct, sys

path = sys.argv[1]
d = open(path, 'rb').read()
num = struct.unpack('>H', d[76:78])[0]
records = [struct.unpack('>I', d[78 + i * 8:82 + i * 8])[0] for i in range(num)]

def parse_header(i):
    r = d[records[i]:records[i] + 4096]
    if r[16:20] != b'MOBI':
        return None
    hlen = struct.unpack('>I', r[20:24])[0]
    version = struct.unpack('>I', r[36:40])[0]
    pos = 16 + hlen
    exth = {}
    if r[pos:pos + 4] == b'EXTH':
        _, count = struct.unpack('>II', r[pos + 4:pos + 12])
        q = pos + 12
        for _ in range(count):
            typ, length = struct.unpack('>II', r[q:q + 8])
            exth[typ] = r[q + 8:q + length]
            q += length
    return version, exth

version0, exth0 = parse_header(0)
print('record0 MOBI version:', version0)
print('EXTH 525:', exth0.get(525))
print('EXTH 527:', exth0.get(527))
if 121 in exth0:
    kf8_record = struct.unpack('>I', exth0[121])[0]
    version1, exth1 = parse_header(kf8_record)
    print('joint: KF8 record', kf8_record)
    print('KF8 version:', version1)
    print('KF8 EXTH 525:', exth1.get(525))
    print('KF8 EXTH 527:', exth1.get(527))
else:
    print('EXTH 121 なし: joint ではない')
```

判定：

- `record0 version 6` + `EXTH 121` + KF8 側 `version 8` → joint。Paperwhite で開ける見込み。
- `record0 version 8` + `EXTH 121` なし → KF8 単体。`.mobi` 名では開けない可能性が高い。`.azw3` のまま使うか、joint を作り直す。
- `version 6` + `EXTH 121` なし → MOBI6 単体。縦書き・ruby は保持されない。

元 AZW3（KF8 単体）の例：

```text
record0 MOBI version: 8
EXTH 525: b'vertical-rl'
EXTH 527: b'rtl'
EXTH 121 なし: joint ではない
```

## 3. 変換

### 3.1 標準コマンド（まずはこれ）

```bash
ebook-convert input.azw3 output.mobi \
  --mobi-file-type=both \
  --no-inline-toc \
  --mobi-keep-original-images
```

- `--mobi-file-type=both`：MOBI6 + KF8 の joint を作る。**これが最重要**。
- `--no-inline-toc`：元の NCX 目次がある場合、末尾への目次追加を抑止する。元に目次がない場合は外す。
- `--mobi-keep-original-images`：表紙・挿絵の再エンコードを避ける。

### 3.2 組版を保持する変換（今回使用）

calibre の通常変換は `CSSFlattener` で CSS を平坦化し、フォントサイズを再マッピングする。1,750 分割・24MB 級の本文では 20 分以上かかり、組版が変わる可能性もある。今回は以下のラッパーで `CSSFlattener` を no-op にし、元の XHTML/CSS をそのまま出力した。

```python
#!/usr/bin/env python3
# /tmp/ebook-convert-noflat
import sys, os

path = os.environ.get('CALIBRE_PYTHON_PATH', '/usr/lib/calibre')
if path not in sys.path:
    sys.path.insert(0, path)
sys.resources_location = os.environ.get('CALIBRE_RESOURCES_PATH', '/usr/share/calibre')
sys.extensions_location = os.environ.get('CALIBRE_EXTENSIONS_PATH', '/usr/lib/calibre/calibre/plugins')
sys.executables_location = os.environ.get('CALIBRE_EXECUTABLES_PATH', '/usr/bin')
sys.system_plugins_location = '/usr/share/calibre/system-plugins'

from calibre.ebooks.oeb.transforms import flatcss

class NoFlatten:
    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, oeb, opts):
        try:
            fbase = float(getattr(opts, 'base_font_size', 0) or 12)
        except Exception:
            fbase = 12.0
        opts._final_base_font_size = fbase
        opts._stored_page_margins = {}
        oeb.store_embed_font_rules = None

flatcss.CSSFlattener = NoFlatten

from calibre.ebooks.conversion.cli import main
sys.exit(main())
```

```bash
chmod +x /tmp/ebook-convert-noflat

/tmp/ebook-convert-noflat input.azw3 output.mobi \
  --mobi-file-type=both \
  --no-inline-toc \
  --mobi-keep-original-images
```

注意：

- calibre の内部 API（`flatcss.CSSFlattener`）に依存する。calibre 9.14.0 で動作確認。更新後は要再確認。
- calibre のインストール先が異なる場合は `CALIBRE_PYTHON_PATH` を調整する。
- flattener を飛ばすため、MOBI6 フォールバック側の CSS 最適化（unfloat / untable 等）も省略される。KF8 対応機では KF8 側が使われるので実害はない。
- 出力プロファイルに応じた余白・フォントサイズ調整も省略される。元の組版を優先する場合のトレードオフ。
- まず標準コマンドで結果を確認し、組版が崩れる／時間がかかりすぎる場合にこのラッパーを使う。

変換時間の目安：1,750 分割で合計 25〜30 分。出力は元 8MB に対して約 27MB（joint のため）。

## 4. 検証

### 4.1 joint 構造

```bash
python3 check_mobi.py output.mobi
```

期待例：

```text
record0 MOBI version: 6
joint: KF8 record 4820
KF8 version: 8
KF8 EXTH 525: b'vertical-rl'
KF8 EXTH 527: b'rtl'
```

`record0 version 6`、`EXTH 121`、`BOUNDARY` レコード、KF8 側 `version 8` が揃っていれば joint。

### 4.2 KF8 側の中身

```bash
rm -rf /tmp/kf8check
calibre-debug -c "from calibre.ebooks.mobi.tweak import do_explode; do_explode('output.mobi', '/tmp/kf8check')"
```

`calibre-debug -x` は joint ファイルで「MOBI6 を削除してよいか」と対話プロンプトを出すため、非 TTY では `termios.error` になる。`do_explode` を直接呼ぶ。

確認項目：

```bash
grep -o 'primary-writing-mode[^>]*' /tmp/kf8check/metadata.opf
grep -o '<spine[^>]*>' /tmp/kf8check/metadata.opf
grep -c '<navPoint' /tmp/kf8check/toc.ncx
grep -o '<html[^>]*>' /tmp/kf8check/text/part0004.html
grep -n -A3 '\.vrtl' /tmp/kf8check/styles/0001.css
```

期待：

- `primary-writing-mode" content="vertical-rl"`
- `<spine ... page-progression-direction="rtl">`
- 目次件数が元と一致（例：1,895）
- `<html ... class="vrtl">`
- `.vrtl { -webkit-writing-mode: vertical-rl; ... }`

ruby は行数ではなく出現数で比較する。

```python
import glob

def counts(root):
    ruby = rt = 0
    for path in glob.glob(root + '/text/*.html'):
        s = open(path, encoding='utf-8').read()
        ruby += s.count('<ruby')
        rt += s.count('<rt>')
    return ruby, rt

print('output:', counts('/tmp/kf8check'))
```

元ファイル側も `calibre-debug -x input.azw3 /tmp/sourcecheck`（KF8 単体ならプロンプトなし）で展開し、同じ関数で数える。`ruby` と `rt` の数が一致すれば注音の欠落はない。

表紙は元の画像と SHA-256 を比較する。

```bash
grep -i -A2 'cover' /tmp/kf8check/metadata.opf
sha256sum /tmp/kf8check/images/*.jpeg
```

## 5. Kindle への転送

1. Kindle 内に前回の「開けない版」が残っている場合は先に削除する。同じ書名で重複するため。
2. USB なら `documents/` に `output.mobi` をコピー。
3. LAN 配信なら PC 側で：

```bash
python3 -m http.server 8001 --bind 0.0.0.0 --directory "/path/to/books"
```

Kindle のブラウザで `http://<PC の LAN IP>:8001/` を開き、`.mobi` をダウンロードする。

「転送成功」と「Kindle が解析して開ける」は別。開けない場合は 4.1 の joint 構造を先に疑う。

## 6. 既知の差分・注意

- MOBI6 パートはフォールバック用。縦書き・ruby は KF8 パートで表現される。KF8 非対応の旧機では縦書き・ruby は失われる（形式上の限界）。
- calibre の writer8 は EXTH 113（ASIN）を UUID で再生成する。元の `mobi-asin` は保持されない。タイトル・著者・出版社・日付・表紙・目次は保持される。
- EXTH 528（`override_kindle_fonts`）は calibre が `true` を書く。元が `false` でも変わる。フォント選択の挙動がわずかに変わる。
- joint 化・再レンダリングのためバイト単位の無損失ではない。`.azw3` 原本を無損失マスターとして残す。
- `.azw` 拡張子でも同じ joint コンテナなら動作する。拡張子だけの変更では不可。
- `--mobi-file-type=new` の KF8 単体 `.mobi` は Paperwhite で開けない。`.azw3` のまま使うか、`both` で作り直す。

## 7. 実例（2026-10-26）

- 書名：山本周五郎電子全集（全123作品） 日本文学名作電子全集
- 元：`山本周五郎電子全集.azw3` 8.0MB、KF8、1,750 HTML、ruby 56,871 / rt 56,871、目次 1,895、EXTH 525=`vertical-rl`、527=`rtl`
- 失敗：`--mobi-file-type=new` の 15MB `.mobi`。Paperwhite 第6世代で転送成功・開けない（KF8 単体、BOUNDARY なし）。
- 成功：`--mobi-file-type=both` + no-flat ラッパー、27MB joint。record0 version 6、EXTH 121=4,820、KF8 version 8、KF8 EXTH 525=`vertical-rl` / 527=`rtl`、ruby 56,871 / rt 56,871、目次 1,895、`<html class="vrtl">`、表紙 SHA-256 `cab7703c596674c5eb4a77f6b1e1679ba996df38b4ad3d81ac972931cba1a767`（元と一致）。Kindle で開けることを確認。

## 8. 参考

- calibre Conversion: https://manual.calibre-ebook.com/conversion.html
- calibre の MOBI writer8: `calibre/ebooks/mobi/writer8/`（EXTH 525 / 527 / 121、`page_progression_direction`）
- calibre の MOBI 検査: `calibre.ebooks.mobi.reader.headers.MetadataHeader`、`calibre.ebooks.mobi.tweak.do_explode`
