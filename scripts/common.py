# -*- coding: utf-8 -*-
"""Common utilities: RSS fetching, time formatting, shared dashboard template."""
from __future__ import annotations
import html
import gzip
import json
import os
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HTTP_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",  # avoid gzip decode issues
    "Cache-Control": "no-cache",
}
BEIJING = timezone(timedelta(hours=8))
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
SITE_DIR = os.path.join(PROJECT_ROOT, "site")
DATA_DIR = os.path.join(SITE_DIR, "data")
ARCHIVE_DIR = os.path.join(SITE_DIR, "archive")


# ---------- Time helpers ----------
def now_beijing() -> datetime:
    return datetime.now(BEIJING)


def today_str() -> str:
    return now_beijing().strftime("%Y-%m-%d")


def fmt_beijing(iso_str: str | None) -> str:
    """Convert ISO 8601 (UTC or with offset) to '6月25日 周四 19:30' style."""
    if not iso_str:
        return ""
    try:
        s = iso_str.strip()
        # Handle trailing Z
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        bj = dt.astimezone(BEIJING)
        return f"{bj.month}月{bj.day}日 {WEEKDAYS[bj.weekday()]} {bj.strftime('%H:%M')}"
    except Exception:
        return iso_str[:16].replace("T", " ")


def relative_day(date_str: str) -> str:
    """'2026-06-25' -> '6月25日 周四'."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=BEIJING)
        return f"{dt.month}月{dt.day}日 {WEEKDAYS[dt.weekday()]}"
    except Exception:
        return date_str


# ---------- Network ----------
def http_get(url: str, timeout: int = 30, retries: int = 3) -> bytes:
    """HTTP GET with retry. Raises last exception after all retries exhausted."""
    import time
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HTTP_HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))  # 5s, 10s backoff
    raise last_err


def http_get_json(url: str, timeout: int = 30):
    return json.loads(http_get(url, timeout).decode("utf-8"))


# ---------- RSS ----------
def fetch_rss(url: str, limit: int = 30, source_name: str = "") -> list[dict]:
    """Fetch an RSS/Atom feed and return normalized items.
    Each item: {title, link, summary, source, pub_date(ISO), pub_label}
    Robust against common RSS quirks; never raises (returns [] on failure).
    """
    try:
        payload = http_get(url, timeout=20)
        if payload.startswith(b"\x1f\x8b"):
            payload = gzip.decompress(payload)
        raw = payload.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [RSS WARN] {url}: {e}")
        return []

    items = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f"  [RSS WARN] {url} parse error: {e}")
        return []

    # RSS 2.0: channel/item
    rss_items = root.findall(".//item")
    if rss_items:
        for it in rss_items[:limit]:
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            desc = (it.findtext("description") or "").strip()
            pub = (it.findtext("pubDate") or "").strip()
            # source
            src_el = it.find("source")
            src = src_el.text.strip() if src_el is not None and src_el.text else source_name
            if not src:
                src = source_name
            items.append(_normalize_item(title, link, desc, pub, src))
        return items

    # Atom: feed/entry
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entries = root.findall(".//a:entry", ns)
    for e in entries[:limit]:
        title = (e.findtext("a:title", default="", namespaces=ns) or "").strip()
        link_el = e.find("a:link", ns)
        link = link_el.get("href", "") if link_el is not None else ""
        summary = (e.findtext("a:summary", default="", namespaces=ns) or
                   e.findtext("a:content", default="", namespaces=ns) or "").strip()
        pub = (e.findtext("a:updated", default="", namespaces=ns) or
               e.findtext("a:published", default="", namespaces=ns) or "").strip()
        src = source_name
        items.append(_normalize_item(title, link, summary, pub, src))
    return items


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(s: str) -> str:
    s = _TAG_RE.sub("", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def _normalize_item(title, link, desc, pub, src) -> dict:
    title = _strip_html(title)
    desc = _strip_html(desc)
    # Parse pub date
    iso = ""
    label = pub
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(pub, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            iso = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            label = fmt_beijing(iso)
            break
        except ValueError:
            continue
    return {
        "title": title,
        "link": link,
        "summary": desc,
        "source": src,
        "pub_date": iso,
        "pub_label": label,
    }


# ---------- Text helpers ----------
def trunc(s: str, n: int = 60) -> str:
    s = (s or "").replace("\n", " ").replace("\r", " ").strip()
    return (s[:n] + "…") if len(s) > n else s


def esc(s) -> str:
    return html.escape(s or "", quote=True)


def classify(text: str, rules: list[tuple[str, list[str]]], default: str) -> str:
    """Match text against keyword rules; first match wins.
    rules: [(category, [kw1, kw2, ...]), ...]
    """
    t = text.lower()
    for cat, kws in rules:
        for kw in kws:
            if kw.lower() in t:
                return cat
    return default


# ---------- HTML rendering ----------
SHARED_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#f6f7fb;--card:#fff;--ink:#1a1f36;--muted:#6b7280;--line:#e5e7eb;--soft:#f1f3f9}
html{scroll-behavior:smooth}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--ink);line-height:1.6}
.hero{color:#fff;padding:56px 24px 44px;position:relative;overflow:hidden}
.hero::before{content:"";position:absolute;inset:0;background-image:radial-gradient(circle at 20% 20%,rgba(255,255,255,.10) 0,transparent 40%),radial-gradient(circle at 80% 70%,rgba(255,255,255,.08) 0,transparent 45%);pointer-events:none}
.hero-inner{max-width:1200px;margin:0 auto;position:relative;z-index:1}
.hero-tag{display:inline-block;font-size:12px;letter-spacing:2px;background:rgba(255,255,255,.16);padding:5px 12px;border-radius:20px;margin-bottom:14px}
.hero h1{font-size:34px;font-weight:800;letter-spacing:1px;margin-bottom:10px}
.hero-sub{font-size:15px;opacity:.85;margin-bottom:24px}
.hero-meta{display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin-bottom:26px;font-size:14px}
.hero-meta .pill{background:rgba(255,255,255,.15);padding:6px 14px;border-radius:18px}
.hero-meta .pill b{font-size:20px;font-weight:800;margin-right:4px}
.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}
.stat{background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.18);border-radius:14px;padding:14px 10px;text-align:center;backdrop-filter:blur(4px)}
.stat-num{font-size:26px;font-weight:800;color:#fff}
.stat-num::before{content:"";display:block;width:28px;height:3px;background:var(--accent);border-radius:2px;margin:0 auto 8px}
.stat-label{font-size:12px;opacity:.9;margin-top:4px}
.nav{position:sticky;top:0;z-index:50;background:rgba(255,255,255,.92);backdrop-filter:blur(10px);border-bottom:1px solid var(--line);display:flex;gap:6px;padding:10px 16px;overflow-x:auto;justify-content:center;flex-wrap:wrap}
.nav-item{display:inline-flex;align-items:center;gap:6px;text-decoration:none;padding:7px 14px;border-radius:20px;font-size:13px;color:var(--ink);background:var(--soft);border:1px solid transparent;transition:.18s;white-space:nowrap}
.nav-item:hover{border-color:var(--accent);color:var(--accent)}
.nav-item.active{background:var(--accent);color:#fff}
.nav-en{font-size:11px;opacity:.55}
.nav-cnt{font-size:11px;background:rgba(0,0,0,.08);padding:1px 7px;border-radius:10px;font-weight:700}
.nav-item.active .nav-cnt{background:rgba(255,255,255,.25)}
.wrap{max-width:1200px;margin:0 auto;padding:36px 20px 60px}
.sec{margin-bottom:48px;scroll-margin-top:64px}
.sec-head{display:flex;align-items:center;gap:12px;margin-bottom:20px}
.sec-bar{width:6px;height:26px;background:var(--accent);border-radius:3px}
.sec-head h2{font-size:22px;font-weight:800}
.sec-en{font-size:13px;font-weight:500;color:var(--muted);margin-left:6px}
.sec-count{margin-left:auto;font-size:13px;color:var(--accent);font-weight:700;background:var(--soft);padding:4px 12px;border-radius:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 18px 14px;display:flex;flex-direction:column;gap:10px;transition:.2s;position:relative;overflow:hidden}
.card::before{content:"";position:absolute;top:0;left:0;width:4px;height:100%;background:var(--accent);opacity:.85}
.card:hover{transform:translateY(-3px);box-shadow:0 10px 30px rgba(30,27,75,.10);border-color:var(--accent)}
.card-top{display:flex;align-items:center;gap:10px}
.num{display:inline-flex;align-items:center;justify-content:center;min-width:30px;height:24px;padding:0 8px;border-radius:12px;color:#fff;font-size:12px;font-weight:800}
.date{font-size:12px;color:var(--muted)}
.title{font-size:15.5px;font-weight:700;line-height:1.45;color:var(--ink)}
.summary{font-size:13px;color:#4b5563;line-height:1.6;flex:1}
.card-foot{display:flex;align-items:center;gap:8px;margin-top:4px}
.chip{font-size:11px;color:#6b7280;background:var(--soft);padding:3px 10px;border-radius:10px;max-width:70%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.link{margin-left:auto;font-size:12px;font-weight:600;color:var(--accent);text-decoration:none;padding:4px 10px;border:1px solid var(--accent);border-radius:14px;transition:.15s}
.link:hover{background:var(--accent);color:#fff}
.foot{max-width:1200px;margin:0 auto;padding:28px 20px 50px;text-align:center;color:var(--muted);font-size:12.5px;border-top:1px solid var(--line)}
.foot b{color:var(--ink)}
.foot a{color:#3730a3;text-decoration:none}
.note{max-width:1200px;margin:0 auto;padding:14px 18px;color:var(--muted);font-size:11.5px;line-height:1.7;background:#fffbeb;border:1px solid #fde68a;border-radius:10px}
.back-home{display:inline-block;margin:14px 20px 0;padding:6px 14px;background:#fff;border:1px solid var(--line);border-radius:18px;font-size:13px;color:#3730a3;text-decoration:none}
.back-home:hover{background:#3730a3;color:#fff}
@media(max-width:720px){.hero{padding:40px 18px 32px}.hero h1{font-size:26px}.stats{grid-template-columns:repeat(5,1fr);gap:6px}.stat{padding:10px 4px}.stat-num{font-size:18px}.stat-label{font-size:10px}.grid{grid-template-columns:1fr}.nav{justify-content:flex-start}}
"""

NAV_JS = """
const navItems=document.querySelectorAll('.nav-item');const map=new Map();
navItems.forEach(n=>map.set(n.getAttribute('href').slice(1),n));
const obs=new IntersectionObserver(e=>{e.forEach(x=>{if(x.isIntersecting){navItems.forEach(n=>n.classList.remove('active'));const t=map.get(x.target.id);if(t)t.classList.add('active');}})},{rootMargin:'-80px 0px -70% 0px',threshold:0});
document.querySelectorAll('.sec').forEach(s=>obs.observe(s));
"""


def render_dashboard(*, title: str, tag: str, subtitle: str,
                     gradient: str, date_range: str, period_label: str,
                     sections: list[dict], footer_source: str,
                     footer_note: str = "") -> str:
    """Render a single dashboard HTML page.

    sections: [
      {id, zh, en, color, items: [
        {date_label, title, summary, source, url}
      ]}
    ]
    """
    counter = 0
    section_blocks = []
    nav_html_parts = []
    stat_html_parts = []
    total = 0
    for sec in sections:
        total += len(sec["items"])
    for sec in sections:
        sid = sec["id"]; zh = sec["zh"]; en = sec["en"]; color = sec["color"]
        items = sec["items"]
        cards = []
        for it in items:
            counter += 1
            cards.append(f"""
    <article class="card" style="--accent:{color}">
      <div class="card-top">
        <span class="num" style="background:{color}">{counter}</span>
        <span class="date">{esc(it['date_label'])}</span>
      </div>
      <h3 class="title">{esc(it['title'])}</h3>
      <p class="summary">{esc(trunc(it['summary'], 60))}</p>
      <div class="card-foot">
        <span class="chip" title="{esc(it['source'])}">{esc(it['source'])}</span>
        <a class="link" href="{esc(it['url'])}" target="_blank" rel="noopener noreferrer">原文 ↗</a>
      </div>
    </article>""")
        nav_html_parts.append(
            f'<a class="nav-item" href="#{sid}" style="--accent:{color}"><span class="nav-zh">{esc(zh)}</span><span class="nav-en">{esc(en)}</span><span class="nav-cnt">{len(items)}</span></a>'
        )
        stat_html_parts.append(
            f'<div class="stat" style="--accent:{color}"><div class="stat-num">{len(items)}</div><div class="stat-label">{esc(zh)}</div></div>'
        )
        section_blocks.append(f"""
  <section id="{sid}" class="sec">
    <div class="sec-head" style="--accent:{color}">
      <span class="sec-bar"></span>
      <h2>{esc(zh)}<span class="sec-en">/ {esc(en)}</span></h2>
      <span class="sec-count">{len(items)} 条</span>
    </div>
    <div class="grid">
{chr(10).join(cards)}
    </div>
  </section>""")

    nav_html = "\n".join(nav_html_parts)
    stat_html = "\n".join(stat_html_parts)
    sections_html = "\n".join(section_blocks)
    note_html = f'<div class="note">{esc(footer_note)}</div>' if footer_note else ""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<style>{SHARED_CSS}
.hero{{background:{gradient}}}</style>
</head>
<body>
<header class="hero">
  <div class="hero-inner">
    <span class="hero-tag">{esc(tag)}</span>
    <h1>{esc(title)}</h1>
    <div class="hero-sub">{esc(subtitle)}</div>
    <div class="hero-meta">
      <span class="pill">{period_label} <b>{esc(date_range)}</b></span>
      <span class="pill">总条数 <b>{total}</b></span>
    </div>
    <div class="stats">
{stat_html}
    </div>
  </div>
</header>
<a class="back-home" href="../index.html">← 返回首页</a>
<nav class="nav">
{nav_html}
</nav>
<main class="wrap">
{sections_html}
{note_html}
</main>
<footer class="foot">
  <p>本期共收录 <b>{total}</b> 条要闻，覆盖 {esc(date_range)}。</p>
  <p style="margin-top:6px">数据来源：{esc(footer_source)} · 时间均为北京时间</p>
</footer>
<script>{NAV_JS}</script>
</body>
</html>"""


def write_meta(name: str, meta: dict) -> None:
    """Persist dashboard metadata for index page builder."""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"{name}.json")
    # Merge with existing if present (we always overwrite latest)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def save_dashboard(name: str, html_str: str, date_str: str) -> None:
    """Save current + archived copy for a dashboard."""
    # current
    cur_path = os.path.join(SITE_DIR, name, "index.html")
    os.makedirs(os.path.dirname(cur_path), exist_ok=True)
    with open(cur_path, "w", encoding="utf-8") as f:
        f.write(html_str)
    # archive
    arch_dir = os.path.join(ARCHIVE_DIR, date_str)
    os.makedirs(arch_dir, exist_ok=True)
    with open(os.path.join(arch_dir, f"{name}.html"), "w", encoding="utf-8") as f:
        f.write(html_str)
    print(f"  -> {cur_path}")
    print(f"  -> {os.path.join(arch_dir, name + '.html')}")
