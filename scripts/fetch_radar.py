# -*- coding: utf-8 -*-
"""ai-radar main pipeline.

Fetch sources -> dedup -> grade S/A/B/C (LLM, keyword fallback)
-> render dual-channel dashboard -> sediment high-value items into skills/.

Channels:
  ai    = AI 工具与变现
  media = 自媒体与个人成长
"""
from __future__ import annotations
import json
import os
import re
import sys
from datetime import timedelta

from common import (http_get, http_get_json, today_str, now_beijing,
                    fmt_beijing, save_dashboard, write_meta, esc, trunc,
                    SHARED_CSS, NAV_JS, SITE_DIR, PROJECT_ROOT)
import llm

# ---------- Tolerant RSS (some CN feeds are GBK or contain bad entities) ----------
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_BAD_ENT_RE = re.compile(r"&(?!amp;|lt;|gt;|quot;|apos;|#)")


def fetch_rss(url: str, limit: int = 25, source_name: str = "") -> list[dict]:
    """Encoding/entity-tolerant RSS fetcher; mirrors common.fetch_rss output."""
    import gzip
    from xml.etree import ElementTree as ET

    try:
        payload = http_get(url, timeout=20)
        if payload.startswith(b"\x1f\x8b"):
            payload = gzip.decompress(payload)
    except Exception as e:
        print(f"  [RSS WARN] {url}: {e}")
        return []

    raw = None
    for enc in ("utf-8", "gb18030"):
        try:
            raw = payload.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if raw is None:
        raw = payload.decode("utf-8", errors="replace")
    raw = _CTRL_RE.sub("", raw)
    raw = _BAD_ENT_RE.sub("&amp;", raw)
    # strip DOCTYPE that may reference unreachable DTDs
    raw = re.sub(r"<!DOCTYPE[^>]*>", "", raw, flags=re.I)

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        # Last resort: regex per-item extraction (tolerates broken feed-level XML)
        return _regex_items(raw, limit, source_name, url)

    from common import _normalize_item
    items = []
    rss_items = root.findall(".//item")
    if rss_items:
        for it in rss_items[:limit]:
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            desc = (it.findtext("description") or "").strip()
            pub = (it.findtext("pubDate") or "").strip()
            items.append(_normalize_item(title, link, desc, pub, source_name))
        return items

    ns = {"a": "http://www.w3.org/2005/Atom"}
    for e in root.findall(".//a:entry", ns)[:limit]:
        title = (e.findtext("a:title", default="", namespaces=ns) or "").strip()
        link_el = e.find("a:link", ns)
        link = link_el.get("href", "") if link_el is not None else ""
        summary = (e.findtext("a:summary", default="", namespaces=ns) or
                   e.findtext("a:content", default="", namespaces=ns) or "").strip()
        pub = (e.findtext("a:updated", default="", namespaces=ns) or
               e.findtext("a:published", default="", namespaces=ns) or "").strip()
        items.append(_normalize_item(title, link, summary, pub, source_name))
    return items


def _cdata_unwrap(s: str) -> str:
    s = s.strip()
    if s.startswith("<![CDATA[") and s.endswith("]]>"):
        return s[9:-3]
    return s


def _regex_items(raw: str, limit: int, source_name: str, url: str) -> list[dict]:
    from common import _normalize_item
    items = []
    blocks = re.findall(r"<item\b[^>]*>(.*?)</item>", raw, re.S | re.I)
    if not blocks:
        print(f"  [RSS WARN] {url}: no <item> blocks recoverable")
        return []
    for b in blocks[:limit]:
        def field(tag: str) -> str:
            m = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", b, re.S | re.I)
            return _cdata_unwrap(m.group(1)) if m else ""
        items.append(_normalize_item(field("title"), field("link"),
                                     field("description"), field("pubDate"),
                                     source_name))
    print(f"  [RSS INFO] {url}: recovered {len(items)} items via regex fallback")
    return items

AIHOT_API = "https://aihot.virxact.com/api/public"

RSS_SOURCES = [
    # (url, source_name, channel_hint: ai|media|auto)
    # 注：机器之心/36氪官网/虎嗅/品玩/鸟哥笔记 均为 WAF 反爬页，不可用
    ("https://www.qbitai.com/feed", "量子位", "ai"),
    ("https://www.tmtpost.com/rss.xml", "钛媒体", "auto"),
    ("https://www.geekpark.net/rss", "极客公园", "auto"),
    ("https://www.ifanr.com/feed", "爱范儿", "auto"),
    ("https://rsshub.rssforever.com/36kr/newsflashes", "36氪快讯", "auto"),
    ("https://sspai.com/feed", "少数派", "auto"),
    ("https://www.woshipm.com/feed", "人人都是产品经理", "media"),
    ("https://www.yunyingpai.com/feed", "运营派", "media"),
]

CHANNEL_META = {
    "ai":    {"zh": "AI 工具与变现", "en": "AI & Monetization", "color": "#3730a3"},
    "media": {"zh": "自媒体与个人成长", "en": "Creator & Growth", "color": "#b45309"},
}
GRADE_META = {
    "S": ("#dc2626", "可复制实操"),
    "A": ("#ea580c", "高价值洞见"),
    "B": ("#2563eb", "一般资讯"),
    "C": ("#6b7280", "低价值"),
}

MEDIA_KWS = ["自媒体", "小红书", "公众号", "短视频", "抖音", "B站", "UP主", "个人IP",
             "副业", "变现", "涨粉", "私域", "知识付费", "内容创业", "写作", "播客",
             "直播带货", "成长", "认知", "思维", "IP打造", "账号"]
AI_KWS = ["ai", "大模型", "gpt", "claude", "智能体", "agent", "llm", "提示词",
          "模型", "aigc", "deepseek", "openai", "anthropic", "具身", "机器人",
          "copilot", "sora", "midjourney", "自动驾驶"]

S_KWS = ["实操", "教程", "复盘", "月入", "案例", "从0", "保姆级", "方法论", "手把手",
         "收入", "赚了", "拆解", "全流程", "变现路径", "踩坑"]
A_KWS = ["玩法", "技巧", "工具", "指南", "经验", "攻略", "效率", "神器", "工作流",
         "提示词", "模板"]
C_KWS = ["融资", "宣布", "股价", "财报", "市值", "任命", "收购"]

SKILLS_DIR = os.path.join(PROJECT_ROOT, "skills")


# ---------- Fetch ----------
def fetch_aihot(days: int = 2) -> list[dict]:
    """Reuse the aihot API: last N days of AI dailies as raw items."""
    items = []
    today = now_beijing().date()
    for i in range(days):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            data = http_get_json(f"{AIHOT_API}/daily/{d}", timeout=20)
        except Exception as e:
            print(f"  [WARN] aihot {d}: {e}")
            continue
        label = fmt_beijing(data.get("generatedAt", d + "T00:00:00Z"))
        for sec in data.get("sections", []):
            for it in sec.get("items", []):
                items.append({
                    "title": it.get("title", ""),
                    "link": it.get("sourceUrl", "#"),
                    "summary": it.get("summary", ""),
                    "source": f"AI HOT·{it.get('sourceName', '')}",
                    "pub_date": data.get("generatedAt", ""),
                    "pub_label": label,
                    "channel_hint": "ai",
                })
        print(f"  aihot {d}: ok")
    return items


def route_channel(item: dict) -> str:
    hint = item.get("channel_hint")
    if hint in ("ai", "media"):
        return hint
    text = (item.get("title", "") + " " + item.get("summary", "")).lower()
    media_score = sum(1 for kw in MEDIA_KWS if kw.lower() in text)
    ai_score = sum(1 for kw in AI_KWS if kw.lower() in text)
    if media_score > ai_score:
        return "media"
    return "ai" if ai_score > 0 else "media"  # 默认归入成长频道，保证不漏变现信号


def grade_fallback(item: dict) -> str:
    text = item.get("title", "") + " " + item.get("summary", "")
    if any(kw in text for kw in S_KWS):
        return "S"
    if any(kw in text for kw in A_KWS):
        return "A"
    if any(kw in text for kw in C_KWS):
        return "C"
    return "B"


def dedup(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for it in items:
        key = re.sub(r"\W+", "", it.get("title", "").lower())[:40]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


# ---------- Render ----------
def render_radar(*, title, tag, subtitle, gradient, date_label,
                 channels: dict[str, list[dict]], footer_note="") -> str:
    """channels: {'ai': [items], 'media': [items]}; each item has grade/reason/digest."""
    total = sum(len(v) for v in channels.values())
    nav_parts, stat_parts, sec_parts = [], [], []
    for cid, meta in CHANNEL_META.items():
        items = channels.get(cid, [])
        nav_parts.append(
            f'<a class="nav-item" href="#{cid}" style="--accent:{meta["color"]}">'
            f'<span class="nav-zh">{esc(meta["zh"])}</span>'
            f'<span class="nav-en">{esc(meta["en"])}</span>'
            f'<span class="nav-cnt">{len(items)}</span></a>')
        stat_parts.append(
            f'<div class="stat" style="--accent:{meta["color"]}">'
            f'<div class="stat-num">{len(items)}</div>'
            f'<div class="stat-label">{esc(meta["zh"])}</div></div>')
        cards = []
        for it in items:
            g = it.get("grade", "B")
            gcolor, glabel = GRADE_META.get(g, GRADE_META["B"])
            digest = it.get("digest") or trunc(it.get("summary", ""), 80)
            reason = it.get("reason", "")
            reason_html = f'<p class="reason">{esc(reason)}</p>' if reason else ""
            cards.append(f"""
    <article class="card" style="--accent:{gcolor}">
      <div class="card-top">
        <span class="num" style="background:{gcolor}">{g}</span>
        <span class="date">{esc(it.get('pub_label',''))}</span>
        <span class="gtag" style="color:{gcolor};border-color:{gcolor}">{esc(glabel)}</span>
      </div>
      <h3 class="title">{esc(it.get('title',''))}</h3>
      <p class="summary">{esc(digest)}</p>
      {reason_html}
      <div class="card-foot">
        <span class="chip" title="{esc(it.get('source',''))}">{esc(it.get('source',''))}</span>
        <a class="link" href="{esc(it.get('link','#'))}" target="_blank" rel="noopener noreferrer">原文 ↗</a>
      </div>
    </article>""")
        sec_parts.append(f"""
  <section id="{cid}" class="sec">
    <div class="sec-head" style="--accent:{meta['color']}">
      <span class="sec-bar"></span>
      <h2>{esc(meta['zh'])}<span class="sec-en">/ {esc(meta['en'])}</span></h2>
      <span class="sec-count">{len(items)} 条</span>
    </div>
    <div class="grid">
{chr(10).join(cards)}
    </div>
  </section>""")

    grade_legend = "".join(
        f'<span class="pill"><b style="color:{GRADE_META[g][0]}">{g}</b> {esc(GRADE_META[g][1])}</span>'
        for g in ("S", "A", "B", "C"))
    note_html = f'<div class="note">{esc(footer_note)}</div>' if footer_note else ""
    extra_css = """
.gtag{margin-left:auto;font-size:11px;border:1px solid;padding:1px 8px;border-radius:10px;font-weight:700}
.reason{font-size:12px;color:#92400e;background:#fffbeb;border-radius:8px;padding:6px 10px}
.stats{grid-template-columns:repeat(2,1fr)}
"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<style>{SHARED_CSS}{extra_css}
.hero{{background:{gradient}}}</style>
</head>
<body>
<header class="hero">
  <div class="hero-inner">
    <span class="hero-tag">{esc(tag)}</span>
    <h1>{esc(title)}</h1>
    <div class="hero-sub">{esc(subtitle)}</div>
    <div class="hero-meta">
      <span class="pill">更新 <b>{esc(date_label)}</b></span>
      <span class="pill">总条数 <b>{total}</b></span>
      {grade_legend}
    </div>
    <div class="stats">
{chr(10).join(stat_parts)}
    </div>
  </div>
</header>
<a class="back-home" href="../index.html">← 返回首页</a>
<nav class="nav">
{chr(10).join(nav_parts)}
</nav>
<main class="wrap">
{chr(10).join(sec_parts)}
{note_html}
</main>
<footer class="foot">
  <p>本期共收录 <b>{total}</b> 条内容信号 · S/A 级已自动沉淀至 skills/ 技能库</p>
  <p style="margin-top:6px">数据来源：AI HOT / 量子位 / 机器之心 / 36氪 / 少数派 / 虎嗅 · 时间均为北京时间</p>
</footer>
<script>{NAV_JS}</script>
</body>
</html>"""


# ---------- Skill sediment ----------
def slugify(title: str) -> str:
    s = re.sub(r"[^\w一-鿿]+", "-", title).strip("-").lower()
    return s[:50] or "untitled"


def sediment(items: list[dict], date_str: str, max_n: int = 5) -> int:
    """Persist top items as reusable skill notes. Returns count written."""
    day_dir = os.path.join(SKILLS_DIR, date_str)
    written = 0
    for it in items:
        if written >= max_n:
            break
        path = os.path.join(day_dir, slugify(it["title"]) + ".md")
        if os.path.exists(path):
            continue
        body = llm.distill_skill(it)
        if body is None:
            # fallback: structured clipping
            body = (f"# {it['title']}\n\n"
                    f"> 等级：{it.get('grade','?')} · 频道：{CHANNEL_META[it['channel']]['zh']} · "
                    f"来源：{it.get('source','')}\n\n"
                    f"## 摘要\n\n{it.get('digest') or it.get('summary','')}\n\n"
                    f"## 评级理由\n\n{it.get('reason','（关键词模式，无 LLM 理由）')}\n\n"
                    f"来源：{it['title']} {it.get('link','')}\n")
        os.makedirs(day_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        written += 1
        print(f"  [skill] {os.path.relpath(path, PROJECT_ROOT)}")
    return written


# ---------- Main ----------
def main():
    print("[radar] fetching sources...")
    items = fetch_aihot(days=2)
    for url, name, hint in RSS_SOURCES:
        got = fetch_rss(url, limit=25, source_name=name)
        for it in got:
            it["channel_hint"] = hint
        items.extend(got)
        print(f"  {name}: {len(got)} items")

    items = dedup(items)
    print(f"[radar] {len(items)} unique items after dedup")

    # LLM grading (batched), fallback to keyword grading
    graded = None
    if llm.available():
        graded = []
        batch = 20
        for i in range(0, len(items), batch):
            res = llm.grade_items(items[i:i + batch])
            if res is None:
                graded = None
                break
            graded.extend(res)
    if graded:
        for it, g in zip(items, graded):
            it["grade"] = str(g.get("grade", "B")).upper()[:1] if g.get("grade") else "B"
            if it["grade"] not in GRADE_META:
                it["grade"] = "B"
            ch = str(g.get("channel", "")).lower()
            it["channel"] = ch if ch in CHANNEL_META else route_channel(it)
            it["reason"] = g.get("reason", "")
            it["digest"] = g.get("digest", "")
        print("[radar] LLM grading done")
    else:
        for it in items:
            it["grade"] = grade_fallback(it)
            it["channel"] = route_channel(it)
            it["reason"] = ""
            it["digest"] = ""
        print("[radar] keyword grading (LLM unavailable or failed)")

    # sort: grade first, then recency; keep top 30 per channel
    order = {"S": 0, "A": 1, "B": 2, "C": 3}
    channels = {"ai": [], "media": []}
    for it in items:
        channels[it["channel"]].append(it)
    for cid in channels:
        channels[cid].sort(key=lambda x: (order.get(x["grade"], 4), x.get("pub_date", "")), reverse=False)
        channels[cid].sort(key=lambda x: order.get(x["grade"], 4))
        channels[cid] = channels[cid][:30]

    today = today_str()
    date_label = now_beijing().strftime("%m月%d日 %H:%M")
    total = sum(len(v) for v in channels.values())
    llm_note = "" if llm.available() else "未配置 RADAR_API_KEY，当前为关键词评级模式；配置后自动升级为 LLM 智能评级与技能蒸馏。"
    html_str = render_radar(
        title="AI 变现雷达 · 每日信号",
        tag="AI RADAR · DAILY SIGNALS",
        subtitle="监控 AI 玩法与自媒体成长内容，S/A/B/C 四级筛选，高价值方法论自动沉淀为技能。",
        gradient="linear-gradient(135deg,#0f172a 0%,#1e3a5f 50%,#3730a3 100%)",
        date_label=date_label,
        channels=channels,
        footer_note=llm_note,
    )
    save_dashboard("radar", html_str, today)

    # sediment S/A items
    top = [it for v in channels.values() for it in v if it["grade"] in ("S", "A")]
    n = sediment(top, today)

    write_meta("radar", {
        "name": "radar", "title": "AI 变现雷达", "en": "AI Radar",
        "date": today, "total": total,
        "sections": [{"zh": CHANNEL_META[c]["zh"], "en": CHANNEL_META[c]["en"],
                      "count": len(channels[c])} for c in ("ai", "media")],
        "skills_written": n,
        "gradient": "linear-gradient(135deg,#0f172a 0%,#1e3a5f 50%,#3730a3 100%)",
        "tag": "AI RADAR · DAILY",
    })
    print(f"[radar] done. total={total}, skills_written={n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
