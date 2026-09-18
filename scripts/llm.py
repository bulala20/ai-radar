# -*- coding: utf-8 -*-
"""LLM grading + distillation via OpenAI-compatible API (stdlib only).

Config via env:
  RADAR_BASE_URL  default https://api.maitokens.com/v1
  RADAR_API_KEY   required; when absent, all functions fall back to keyword mode
  RADAR_MODEL     default gpt-4o-mini
"""
from __future__ import annotations
import json
import os
import urllib.request

BASE_URL = os.environ.get("RADAR_BASE_URL", "https://api.maitokens.com/v1").rstrip("/")
API_KEY = os.environ.get("RADAR_API_KEY", "").strip()
MODEL = os.environ.get("RADAR_MODEL", "gpt-4o-mini")


def available() -> bool:
    return bool(API_KEY)


def _chat(messages: list[dict], timeout: int = 60) -> str:
    payload = json.dumps({
        "model": MODEL,
        "messages": messages,
        "temperature": 0.2,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
            "User-Agent": "ai-radar/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def _extract_json(text: str):
    """Pull the first JSON array/object out of a model response."""
    text = text.strip()
    for opener, closer in (("[", "]"), ("{", "}")):
        i, j = text.find(opener), text.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(text[i:j + 1])
            except json.JSONDecodeError:
                continue
    return None


GRADE_PROMPT = """你是一个内容价值评估器，服务于一个"AI 变现 + 自媒体成长"雷达系统。
对每条内容给出：
- grade: S / A / B / C
  S = 含可复制的实操路径、真实案例数据、变现方法论
  A = 有明确洞见或新工具/新玩法，值得深入研究
  B = 有价值的一般资讯
  C = 纯新闻、无实操价值
- channel: ai（AI工具与变现）或 media（自媒体与个人成长）
- reason: 一句话中文理由（<=30字）
- digest: 一句话中文摘要（<=40字），提炼最有价值的点

只输出 JSON 数组，与输入顺序一一对应，字段为 grade/channel/reason/digest。"""


def grade_items(items: list[dict]) -> list[dict] | None:
    """Grade a batch of items. Returns None on any failure (caller falls back)."""
    if not available() or not items:
        return None
    lines = []
    for i, it in enumerate(items):
        lines.append(f"{i}. 【{it.get('source','')}】{it.get('title','')} — {it.get('summary','')[:120]}")
    try:
        out = _chat([
            {"role": "system", "content": GRADE_PROMPT},
            {"role": "user", "content": "\n".join(lines)},
        ])
        arr = _extract_json(out)
        if isinstance(arr, list) and len(arr) == len(items):
            return arr
        print(f"  [LLM WARN] grade count mismatch: got {len(arr) if isinstance(arr, list) else 'non-list'}, want {len(items)}")
        return None
    except Exception as e:
        print(f"  [LLM WARN] grade_items failed: {e}")
        return None


DISTILL_PROMPT = """你是方法论蒸馏器。把下面的内容蒸馏成一份可复用的技能笔记（Markdown），要求：
1. 标题即技能名（动词开头，如"用XX做XX"）
2. ## 核心思路（3-5 条要点）
3. ## 操作步骤（编号列表，可执行）
4. ## 适用场景 与 ## 注意事项（各 1-3 条）
5. 末尾附"来源：<标题> <链接>"
只输出 Markdown 正文，不要寒暄。若内容没有可蒸馏的方法论，只输出单词 SKIP。"""


def distill_skill(item: dict) -> str | None:
    """Distill one high-value item into a reusable skill note. None/SKIP -> None."""
    if not available():
        return None
    try:
        out = _chat([
            {"role": "system", "content": DISTILL_PROMPT},
            {"role": "user", "content": f"标题：{item.get('title','')}\n来源：{item.get('source','')} {item.get('link','')}\n摘要：{item.get('summary','')[:600]}"},
        ])
        if not out or out.strip().upper().startswith("SKIP"):
            return None
        return out.strip()
    except Exception as e:
        print(f"  [LLM WARN] distill_skill failed: {e}")
        return None
