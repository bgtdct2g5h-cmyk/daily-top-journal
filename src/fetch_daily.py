#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日顶刊快讯 · 无 AI 自动生成器
流程：RSS/PubMed/arXiv 抓取 -> 免费机翻(DeepL 可选/Google 回退) -> 生成 PWA 站点 + edge-tts 语音
用法：python src/fetch_daily.py [--date YYYY-MM-DD] [--max-per-source N]
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
ARCHIVE = SITE / "archive"
AUDIO = SITE / "audio"
CST = timezone(timedelta(hours=8))

DEFAULT_DATE = datetime.now(CST).strftime("%Y-%m-%d")

# ---------------------------------------------------------------- 来源定义
PUBMED_SOURCES = [
    {"name": "Nature",              "journal": "Nature",                 "issn": "0028-0836"},
    {"name": "Science",             "journal": "Science",                "issn": "0036-8075"},
    {"name": "PNAS",                "journal": "Proc Natl Acad Sci U S A", "issn": "0027-8424"},
    {"name": "The Lancet",          "journal": "The Lancet",             "issn": "0140-6736"},
    {"name": "NEJM",                "journal": "N Engl J Med",           "issn": "0028-4793"},
    {"name": "Cell",                "journal": "Cell",                   "issn": "0092-8674"},
    {"name": "Nature Medicine",     "journal": "Nat Med",                "issn": "1078-8956"},
    {"name": "JAMA",                "journal": "JAMA",                   "issn": "0098-7484"},
    {"name": "MMWR",                "journal": "MMWR Morb Mortal Wkly Rep", "issn": "0149-2195"},
    {"name": "Eurosurveillance",    "journal": "Euro Surveill",          "issn": "1560-7917"},
    {"name": "Lancet Planetary Health", "journal": "Lancet Planet Health", "issn": "2542-5196"},
]
ARXIV_CATS = ["cs.AI", "cs.LG", "cs.CL"]

CATEGORIES = [
    ("综合", ["Nature", "Science", "PNAS"]),
    ("AI 与机器学习", ["arXiv cs.AI", "arXiv cs.LG", "arXiv cs.CL"]),
    ("医学与生命科学", ["The Lancet", "NEJM", "Cell", "Nature Medicine", "JAMA"]),
    ("流行病学", ["MMWR", "Eurosurveillance", "Lancet Planetary Health"]),
]

VOICE = "zh-CN-XiaoxiaoNeural"

# ---------------------------------------------------------------- 网络
def http_get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (daily-journal-bot; +https://github.com/)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")

def http_post_json(url, payload, headers):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode())

# ---------------------------------------------------------------- 抓取
def fetch_pubmed(src, days=6, keep_days=5):
    """PubMed 收录有 1-5 天延迟，故搜索窗口放宽到 days，再按发表日期过滤"""
    term = (f'"{src["issn"]}"[Journal] AND ("last {days} days"[dp])'
            ' AND ("Journal Article"[Publication Type] OR "Review"[Publication Type])')
    url = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
           "?db=pubmed&retmode=json&retmax=8&term=" + urllib.parse.quote(term))
    try:
        data = json.loads(http_get(url))
        ids = data.get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        print(f"  [warn] PubMed esearch {src['name']}: {e}")
        return []
    if not ids:
        return []
    url = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
           "?db=pubmed&id=" + ",".join(ids) + "&rettype=abstract&retmode=xml")
    try:
        xml = http_get(url)
    except Exception as e:
        print(f"  [warn] PubMed efetch {src['name']}: {e}")
        return []
    root = ET.fromstring(xml)
    cutoff = (datetime.now(CST) - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    items = []
    for art in root.findall(".//PubmedArticle"):
        title = " ".join((art.findtext(".//ArticleTitle") or "").split())
        if not title:
            continue
        # 发表日期（ArticleDate 优先，缺失则用 PubDate 年份）
        y = art.findtext(".//ArticleDate/Year", "") or art.findtext(".//PubDate/Year", "")
        m = art.findtext(".//ArticleDate/Month", "") or "01"
        d = art.findtext(".//ArticleDate/Day", "") or "01"
        pub_date = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
        if len(pub_date) == 10 and pub_date < cutoff:
            continue
        abstract = " ".join(t.text or "" for t in art.findall(".//AbstractText"))
        pmid = art.findtext(".//PMID", "")
        doi = ""
        for aid in art.findall(".//ArticleId"):
            if aid.get("IdType") == "doi":
                doi = aid.text or ""
        items.append({
            "journal": src["name"],
            "title": title,
            "abstract": " ".join(abstract.split()),
            "date": pub_date,
            "pmid": pmid,
            "doi": doi,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
        })
    return items

def fetch_arxiv(cat, days=3):
    url = ("http://export.arxiv.org/api/query?search_query=cat:" + cat +
           "&sortBy=submittedDate&sortOrder=descending&max_results=5")
    try:
        xml = http_get(url)
    except Exception as e:
        print(f"  [warn] arXiv {cat}: {e}")
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(xml)
    items = []
    cutoff = (datetime.now(CST) - timedelta(days=days)).strftime("%Y-%m-%d")
    for e in root.findall("a:entry", ns):
        published = (e.findtext("a:published", "", ns) or "")[:10]
        if published < cutoff:
            continue
        title = " ".join((e.findtext("a:title", "", ns) or "").split())
        summary = " ".join((e.findtext("a:summary", "", ns) or "").split())
        link = e.findtext("a:id", "", ns)
        aid = link.rsplit("/", 1)[-1]
        items.append({
            "journal": f"arXiv {cat}",
            "title": title,
            "abstract": summary,
            "date": published,
            "url": f"https://arxiv.org/abs/{aid}",
            "arxiv_id": aid,
        })
    return items

# ---------------------------------------------------------------- 翻译（免费）
def translate(text, max_len=900):
    if not text:
        return ""
    text = text[:max_len]
    key = os.environ.get("DEEPL_API_KEY", "").strip()
    if key:
        try:
            data = http_post_json("https://api-free.deepl.com/v2/translate",
                                  {"text": [text], "target_lang": "ZH"},
                                  {"Content-Type": "application/json",
                                   "Authorization": f"DeepL-Auth-Key {key}"})
            return "".join(x.get("text", "") for x in data.get("translations", []))
        except Exception as e:
            print(f"  [warn] DeepL 失败，回退 Google: {e}")
    # 有道智云 demo（国内可达，无 key，失败重试 2 次）
    for attempt in range(3):
        try:
            url = ("https://aidemo.youdao.com/trans?" + urllib.parse.urlencode(
                {"q": text, "from": "en", "to": "zh-CHS"}))
            data = json.loads(http_get(url, timeout=15))
            if data.get("errorCode") == "0" and data.get("translation"):
                return data["translation"][0]
        except Exception as e:
            if attempt == 2:
                print(f"  [warn] 有道翻译失败: {e}")
        time.sleep(1)
    # MyMemory（免费无 key）
    try:
        url = ("https://api.mymemory.translated.net/get?" + urllib.parse.urlencode(
            {"q": text, "langpair": "en|zh-CN"}))
        data = json.loads(http_get(url, timeout=15))
        t = data.get("responseData", {}).get("translatedText")
        if data.get("responseStatus") == 200 and t:
            return t
    except Exception as e:
        print(f"  [warn] MyMemory 翻译失败: {e}")
    # Google（海外 GitHub Actions 环境可用）
    try:
        url = ("https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q="
               + urllib.parse.quote(text))
        data = json.loads(http_get(url))
        out = "".join(seg[0] for seg in data[0] if seg and seg[0])
        return out or text
    except Exception as e:
        print(f"  [warn] Google 翻译失败，保留原文: {e}")
        return text

# ---------------------------------------------------------------- 语音
def tts(text, out_path):
    try:
        subprocess.run([sys.executable, "-m", "edge_tts", "--voice", VOICE,
                        "--text", text, "--write-media", str(out_path)],
                       check=True, capture_output=True, timeout=180)
        return out_path.stat().st_size > 1000
    except Exception as e:
        print(f"  [warn] TTS 失败: {e}")
        return False

# ---------------------------------------------------------------- HTML
def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

def render_item(idx, it, audio_path, date_str, prefix=""):
    summary = esc(it["title_zh"])
    extra = ""
    if it.get("abstract_zh"):
        extra = f"<p class=\"abs\">{esc(it['abstract_zh'])}</p>"
    link = it["url"] or f"https://doi.org/{it['doi']}"
    source = f"【{esc(it['journal'])}】"
    audio = ""
    if audio_path and audio_path.exists():
        audio_url = f"{prefix}audio/{date_str}/{audio_path.name}"
        audio = (f"<audio controls preload=\"none\" src=\"{audio_url}\"></audio>"
                 f"<button class=\"play\" data-audio=\"{audio_url}\">▶ 朗读本条</button>")
    else:
        audio = "<p class=\"noaudio\">（今日语音生成中，稍后可用）</p>"
    return f"""<details>
<summary>{source}{summary}</summary>
<div class="body">
{extra}
<p class="link">原文：<a href="{esc(link)}" target="_blank" rel="noopener">{esc(link)}</a></p>
{audio}
</div>
</details>"""

def render_page(date_str, groups, archives, is_index=True):
    prefix = "" if is_index else "../"
    nav = f'<a href="{prefix}index.html">今天</a>'
    for d in sorted(archives, reverse=True):
        if d != date_str:
            nav += f' | <a href="{prefix}archive/{d}.html">{d}</a>'
    body = ""
    n = 0
    for gname, items in groups:
        if not items:
            continue
        body += f"<h2>▍{gname}</h2>\n"
        for it in items:
            n += 1
            body += render_item(n, it, AUDIO / date_str / f"{n}.mp3", date_str, prefix) + "\n"
    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>顶刊快讯 · {date_str}</title>
<link rel="manifest" href="{prefix}manifest.webmanifest">
<link rel="icon" href="{prefix}icon-192.png">
<link rel="apple-touch-icon" href="{prefix}icon-192.png">
<meta name="theme-color" content="#0f172a">
<link rel="stylesheet" href="{prefix}styles.css">
</head>
<body>
<header>
<h1>📅 顶刊快讯 · {date_str}</h1>
<p class="sub">主流顶刊每日中文快讯 · 无 AI 自动生成 · {nav}</p>
<button id="playAll">🔊 连播全部语音</button>
</header>
<main>
{body}
</main>
<footer>
<p>免费全文优先级：arXiv → PMC → 期刊 Open Access → 作者预印本。</p>
<p>数据来源：PubMed / arXiv / 期刊公开页（免费）｜语音：edge-tts</p>
</footer>
<script src="{prefix}app.js"></script>
</body>
</html>"""
    return page

def ensure_icons():
    """用 Pillow 生成 PWA 图标（未安装则跳过）"""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("  [warn] Pillow 未安装，跳过图标生成")
        return
    for size in (192, 512):
        path = SITE / f"icon-{size}.png"
        if path.exists():
            continue
        img = Image.new("RGBA", (size, size), (15, 23, 42, 255))
        d = ImageDraw.Draw(img)
        r = size * 0.42
        cx, cy = size * 0.5, size * 0.42
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(56, 189, 248, 255))
        lw = max(2, size // 64)
        for k, (y, w) in enumerate([(0.55, 0.52), (0.68, 0.62), (0.81, 0.72)]):
            x0 = size * (0.5 - w / 2)
            x1 = size * (0.5 + w / 2)
            d.rounded_rectangle([x0, size * y, x1, size * y + lw], radius=lw, fill=(255, 255, 255, 255))
        img.save(path)
        print(f"  生成图标 icon-{size}.png")

# ---------------------------------------------------------------- 主流程
def main():
    args = [a for a in sys.argv[1:]]
    date_str = DEFAULT_DATE
    max_per_source = 4
    if "--date" in args:
        date_str = args[args.index("--date") + 1]
    if "--max-per-source" in args:
        max_per_source = int(args[args.index("--max-per-source") + 1])

    print(f"== 开始生成 {date_str} ==")
    all_items = []
    for src in PUBMED_SOURCES:
        print(f"- 抓取 PubMed: {src['name']}")
        for it in fetch_pubmed(src)[:max_per_source]:
            all_items.append(it)
        time.sleep(0.5)
    for cat in ARXIV_CATS:
        print(f"- 抓取 arXiv: {cat}")
        for it in fetch_arxiv(cat, days=3)[:max_per_source]:
            all_items.append(it)
        time.sleep(0.5)

    print(f"共抓取 {len(all_items)} 条，开始翻译…")
    for i, it in enumerate(all_items):
        it["title_zh"] = translate(it["title"], max_len=400)
        time.sleep(0.8)
        it["abstract_zh"] = translate(it["abstract"], max_len=900)
        time.sleep(0.8)
        print(f"  [{i+1}/{len(all_items)}] {it['journal']}: {it['title_zh'][:40]}")

    groups = []
    for gname, jnames in CATEGORIES:
        items = [it for it in all_items if it["journal"] in jnames][:6]
        groups.append((gname, items))

    SITE.mkdir(parents=True, exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    ensure_icons()
    (AUDIO / date_str).mkdir(parents=True, exist_ok=True)

    print("生成语音…")
    n = 0
    for gname, items in groups:
        for it in items:
            n += 1
            out_path = AUDIO / date_str / f"{n}.mp3"
            if out_path.exists() and out_path.stat().st_size > 1000:
                continue
            text = f"【{it['journal']}】{it['title_zh']}。{it['abstract_zh']}"[:1200]
            ok = tts(text, out_path)
            if not ok:
                print(f"  [warn] 语音失败 {gname} #{n}")
            time.sleep(0.5)

    archives = sorted(p.stem for p in ARCHIVE.glob("*.html"))
    if date_str not in archives:
        archives.append(date_str)

    index_html = render_page(date_str, groups, archives, is_index=True)
    (SITE / "index.html").write_text(index_html, encoding="utf-8")
    arch_html = render_page(date_str, groups, archives, is_index=False)
    (ARCHIVE / f"{date_str}.html").write_text(arch_html, encoding="utf-8")

    n = 0
    for gname, items in groups:
        for it in items:
            n += 1
            it["audio"] = f"audio/{date_str}/{n}.mp3"
    data = {
        "date": date_str,
        "generated_at": datetime.now(CST).isoformat(timespec="seconds"),
        "groups": [[gname, items]
                   for gname, items in groups],
    }
    (SITE / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    total = sum(len(items) for _, items in groups)
    print(f"完成：{date_str}，{total} 条，已写入 site/（index.html + data.json + audio/）")

if __name__ == "__main__":
    main()