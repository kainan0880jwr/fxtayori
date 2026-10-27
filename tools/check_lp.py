#!/usr/bin/env python3
"""LP の公開前の検査（2026-10-28 プラン・LP レビュー）。標準ライブラリだけで動く。

使い方:
  python3 tools/check_lp.py                          # LP だけを検査
  python3 tools/check_lp.py ~/Projects/fx_tayori/lib/screens/plus_screen.dart
                                                     # アプリのプラスの表の行とも突き合わせる

検査すること:
  1. 公開する HTML に仮の文字（【…】）が残っていない（最終更新日の入れ忘れ。privacy.html で一度起きかけた）
  2. 事実と違いうる断定を書いていない（「必ず届」「すべての発表前アラート」「件数の制限なし」。景品表示法の優良誤認）
  3. 介入の件数を料金表に固定していない（「全386件」のように。介入が1回あれば事実と違う）
  4. 料金表の行が、アプリのプラスの表（_featureTable の rows）の行をすべて含む
  5. 文書ページにも CSP・referrer の meta がある
問題があれば理由を出して終了コード 1。
"""
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["index.html", "privacy.html", "terms.html", "tokushoho.html"]
FORBIDDEN = [
    # 【免責事項】のような見出しは通す。日付・未定の仮の文字だけを止める
    (re.compile(r"【[^】]*(?:日|未定|TBD|XX)[^】]*】"), "仮の文字が残っている（公開の日に入れる）"),
    (re.compile(r"必ず届"), "「必ず届く」と書かない"),
    (re.compile(r"すべての(?:★+の)?発表前アラート"), "「すべての発表前アラート」と書かない（おやすみ・上限で届かないことがある）"),
    (re.compile(r"件数の制限なし"), "「件数の制限なし」と書かない"),
    (re.compile(r"全\s*\d+\s*件"), "件数を固定しない（「すべて（1991年〜）」のように）"),
]


class PricingRows(HTMLParser):
    """table.compare の tbody の行見出し（th scope=row）を集める"""

    def __init__(self):
        super().__init__()
        self.in_compare = False
        self.in_row_head = False
        self.rows = []
        self._buf = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table" and "compare" in (a.get("class") or "").split():
            self.in_compare = True
        elif self.in_compare and tag == "th" and a.get("scope") == "row":
            self.in_row_head = True
            self._buf = ""

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_compare = False
        elif tag == "th" and self.in_row_head:
            self.in_row_head = False
            self.rows.append(self._buf.strip())

    def handle_data(self, data):
        if self.in_row_head:
            self._buf += data


def app_rows(dart_path: Path) -> list[str]:
    src = dart_path.read_text(encoding="utf-8")
    m = re.search(r"Widget _featureTable\(\)\s*\{\s*const rows = \[(.*?)\];", src, re.S)
    if not m:
        raise SystemExit(f"{dart_path}: _featureTable の rows が見つからない")
    return re.findall(r"^\s*\('([^']+)',", m.group(1), re.M)


def main() -> int:
    errors = []
    for name in PAGES:
        text = (ROOT / name).read_text(encoding="utf-8")
        # HTML のコメントは公開されても読まれない前提で除く（説明に禁止語の例を書けるように）
        body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        for pat, why in FORBIDDEN:
            for hit in pat.finditer(body):
                line = body.count("\n", 0, hit.start()) + 1
                errors.append(f"{name}:{line}: {why}: {hit.group(0)}")
        if 'http-equiv="Content-Security-Policy"' not in text or 'name="referrer"' not in text:
            errors.append(f"{name}: CSP・referrer の meta が無い")

    parser = PricingRows()
    parser.feed((ROOT / "index.html").read_text(encoding="utf-8"))
    if not parser.rows:
        errors.append("index.html: 料金の比較表（table.compare）が見つからない")
    if len(sys.argv) > 1:
        # アプリとは言い方を1か所だけ変えている（「経済指標の日程・結果」はアプリの表に無い行）
        missing = [r for r in app_rows(Path(sys.argv[1]).expanduser()) if r not in parser.rows]
        for r in missing:
            errors.append(f"index.html: アプリのプラスの表にある行「{r}」が LP の料金表に無い")

    for e in errors:
        print("NG", e)
    print(f"--- 結果: {'NG ' + str(len(errors)) + ' 件' if errors else 'OK'}（料金表の行: {' / '.join(parser.rows)}）")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
