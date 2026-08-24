# 📅 顶刊快讯 · 手机版（PWA，无 AI）

每天自动生成主流顶刊的中文快讯，支持手机「添加到主屏幕」当 app 用、点开看中文摘要、一键连播语音。

## 完全不用 AI
- 抓取：PubMed E-utilities + arXiv API（全部免费、无需 key）
- 翻译：有道智云 demo（免费、国内可达）→ MyMemory（免费）→ Google（海外 Actions 环境）
- 语音：edge-tts（免费）每条一条 mp3，前端可连播
- 定时：GitHub Actions cron 每天北京时间 08:00 自动抓取→翻译→生成→部署

## 期刊分类
- 综合：Nature、Science、PNAS
- AI 与机器学习：arXiv cs.AI / cs.LG / cs.CL
- 医学与生命科学：Lancet、NEJM、Cell、Nature Medicine、JAMA
- 流行病学：MMWR、Eurosurveillance、Lancet Planetary Health

## 本地运行
```bash
pip install -r requirements.txt
python src/fetch_daily.py --date 2026-08-24   # 生成 site/
# 本地预览：cd site && python -m http.server 8000
```

## GitHub 部署（一次性）
1. 把本仓库推到 GitHub（public）。
2. Settings → Pages → Source 选 **GitHub Actions**。
3. Actions 里手动运行一次 `daily-journal`（或等每天 08:00 自动跑）。
4. 手机浏览器打开 `https://<用户名>.github.io/<仓库名>/` → 分享/添加到主屏幕。

## 可选增强
- 想用 DeepL 提高翻译质量：注册 api-free.deepl.com 免费 key，加到仓库 Settings → Secrets → `DEEPL_API_KEY`，脚本自动优先用 DeepL。
- 改期刊：编辑 `src/fetch_daily.py` 顶部的 `PUBMED_SOURCES` / `ARXIV_CATS` / `CATEGORIES`。

## 说明
- PubMed 收录有 1–5 天延迟，快讯按「最近 5 天内发表」收录，实际滞后可接受。
- 免费全文优先级：arXiv → PMC → 期刊 Open Access → 作者预印本。