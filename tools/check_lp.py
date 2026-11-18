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
  5. 文書ページにも CSP・referrer の meta がある（incident.html を含む）
  6. incident.html の「現在のお知らせ」に最終更新の日付と、「掲載が無い＝障害が無い」と読ませない注記がある（2026-11-11）
  8. 読み物（learn.html）と用語集（glossary.html）の本数・語数が、トップの「新しく増えたこと」の数と同じ。
     JSON-LD の script 要素の中に「</」が無い（本文から script を閉じられない。2026-11-18 セキュリティ・法務・エンジニア）
     手で書いた「基本（N本）」「用語集（N語）」（トップ・llms.txt）も同じ数。llms.txt にも 2 の言葉を使わない。
     よくある質問と、その構造化データ（faq-ld）の質問が同じ
  7. 公開する HTML（旧版の規約を含むすべての *.html）と *.xml に HTML のコメントが無く、HTML の <style> に CSS のコメントが無い。
     ページのソースから誰でも読めるので、
     編集のメモは非公開の FXニュース/output/legal/lp_notes.md に書く（2026-11-16 全体レビュー UI/UX UX-G4）
問題があれば理由を出して終了コード 1。
"""
import re
import sys
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["index.html", "privacy.html", "terms.html", "tokushoho.html", "incident.html", "learn.html", "glossary.html"]
# incident.html に必ず残す言葉（お知らせが無いときの書き方。2026-11-11 法務レビュー）
INCIDENT_REQUIRED = [
    ("最終更新", "「現在のお知らせ」に最終更新の日付が無い"),
    ("示すものではありません", "「掲載が無い場合も、障害が起きていないことを示すものではありません」が無い"),
]
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


def _text(h: str) -> str:
    """タグとリンク先を除いた文（FAQ の比較用）"""
    t = re.sub(r"<[^>]+>", "", h)
    return re.sub(r"\s+", " ", unescape(t)).strip()


def main() -> int:
    errors = []
    for name in PAGES:
        text = (ROOT / name).read_text(encoding="utf-8")
        # 念のためコメントを除いてから見る（コメントそのものは下の 7 で止める）
        body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        for pat, why in FORBIDDEN:
            for hit in pat.finditer(body):
                line = body.count("\n", 0, hit.start()) + 1
                errors.append(f"{name}:{line}: {why}: {hit.group(0)}")
        if 'http-equiv="Content-Security-Policy"' not in text or 'name="referrer"' not in text:
            errors.append(f"{name}: CSP・referrer の meta が無い")
        if name == "incident.html":
            for word, why in INCIDENT_REQUIRED:
                if word not in body:
                    errors.append(f"{name}: {why}")

    for page in sorted([*ROOT.glob("*.html"), *ROOT.glob("*.xml")]):
        text = page.read_text(encoding="utf-8")
        hits = [m.start() for m in re.finditer(r"<!--", text)]
        for style in re.finditer(r"<style\b.*?</style>", text, re.S):
            hits += [style.start() + m.start() for m in re.finditer(r"/\*", style.group(0))]
        for pos in sorted(hits):
            line = text.count("\n", 0, pos) + 1
            errors.append(f"{page.name}:{line}: コメントを残さない（メモは FXニュース/output/legal/lp_notes.md に）")

    index = (ROOT / "index.html").read_text(encoding="utf-8")
    learn = (ROOT / "learn.html").read_text(encoding="utf-8")
    glossary = (ROOT / "glossary.html").read_text(encoding="utf-8")
    n_primer = len(re.findall(r'<section aria-labelledby="(?!cat-)', learn))
    n_terms = len(re.findall(r"<dt id=", glossary))
    for label, n, unit in (("はじめての経済指標", n_primer, "本の読み物"), ("用語集", n_terms, "語")):
        m = re.search(label + r"</a></b><span>(\d+)" + unit, index)
        if not m or int(m.group(1)) != n:
            errors.append(f"index.html: 「新しく増えたこと」の{label}の数が、生成したページ（{n}{unit}）と合わない")
    # 手で書いた「基本（N本）」「用語集（N語）」も、トップ・llms.txt で生成したページと同じ数か
    for name in ("index.html", "llms.txt", "llms-full.txt"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for m in re.finditer(r"基本（(\d+)本）", text):
            if int(m.group(1)) != n_primer:
                errors.append(f"{name}: 「基本（{m.group(1)}本）」が生成したページ（{n_primer}本）と合わない")
        for m in re.finditer(r"用語集（(\d+)語）", text):
            if int(m.group(1)) != n_terms:
                errors.append(f"{name}: 「用語集（{m.group(1)}語）」が生成したページ（{n_terms}語）と合わない")
        if name.endswith(".txt"):
            for pat, why in FORBIDDEN:
                for hit in pat.finditer(text):
                    errors.append(f"{name}: {why}: {hit.group(0)}")
    # よくある質問の構造化データが、ページの質問と同じ数・同じ順か（build_learn_pages.py が作る）
    sec = re.search(r'<section id="faq".*?</section>', index, re.S)
    page_q = [(_text(q), _text(a)) for q, a in re.findall(
        r'<details[^>]*>\s*<summary>(.*?)</summary>\s*<div class="a">(.*?)</div>\s*</details>', sec.group(0) if sec else "", re.S)]
    ld = re.search(r'<script type="application/ld\+json" id="faq-ld">(.*?)</script>', index, re.S)
    ld_q = []
    if ld:
        for e in json.loads(ld.group(1)).get("mainEntity", []):
            ld_q.append((_text(e["name"]), _text(re.sub(r"（(?:https?|mailto):[^）]*）", "", e["acceptedAnswer"]["text"]))))
    if not page_q or page_q != ld_q:
        errors.append("index.html: よくある質問と構造化データ（faq-ld）の質問・答えが合わない。build_learn_pages.py で作り直す")
    # llms*.txt のリンクは、このサイトと App Store・Google Play・テスターの Google グループだけ（改ざんで外への誘導を入れられないように。セキュリティ 🟡2）
    allowed = ("https://kainan0880jwr.github.io/fxtayori/", "https://apps.apple.com/", "https://play.google.com/apps/testing/jp.fxtayori.app",
               "https://groups.google.com/g/fxtayori-testers")
    for name in ("llms.txt", "llms-full.txt"):
        for u in re.findall(r"https?://[^\s)（）]+", (ROOT / name).read_text(encoding="utf-8")):
            if not u.startswith(allowed):
                errors.append(f"{name}: 許可していない URL: {u}")

    for page in sorted(ROOT.glob("*.html")):
        for sc in re.finditer(r"<script\b[^>]*>(.*?)</script>", page.read_text(encoding="utf-8"), re.S):
            if "</" in sc.group(1) or "<!--" in sc.group(1):
                errors.append(f"{page.name}: script 要素の中に「</」か「<!--」がある（JSON-LD は < を \\u003c にする）")

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
