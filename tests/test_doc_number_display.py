#!/usr/bin/env python3
"""发文字号展示回归（1.7.4）：单路原始 JSON 与 merge 归一 JSON 都要显示文号。

背景：1.7.3 的 renderer 只读 `文号`/`doc_number`，而可信 V2 原始字段是
`发文字号`、深搜 V3 原始字段是 `writtenText`；单路直接渲染不经过 merge，
导致知识专库高可信卡片漏显文号。本测试同时覆盖两条路径。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import merge_search_results as m  # noqa: E402
import render_trace_html as r  # noqa: E402

passed = 0
failed = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  ok   {name}")
    else:
        failed += 1
        print(f"  FAIL {name} {detail}")


def source(item: dict) -> dict:
    return r.source_from_article(item, 1)


# 1) 可信 V2 单路原始 JSON：文章级字段是 发文字号
s = source({
    "文章标题": "国务院关于印发《推动大规模设备更新和消费品以旧换新行动方案》的通知",
    "文章类型": "policy",
    "发文字号": "国发〔2024〕7号",
    "文号": None,
    "doc_number": None,
})
check("V2 单路原始 发文字号 可见", s["doc_number"] == "国发〔2024〕7号", s["doc_number"])

# 2) 深搜 V3 单路原始 JSON：文章级字段是 writtenText
s = source({
    "文章标题": "国务院关于印发《推动大规模设备更新和消费品以旧换新行动方案》的通知",
    "文章类型": "policy",
    "writtenText": "国发〔2024〕7号",
})
check("深搜单路 writtenText 可见", s["doc_number"] == "国发〔2024〕7号", s["doc_number"])

# 3) merge 归一后的 JSON：字段是 文号（回归既有路径）
a = m._to_article({
    "文章标题": "国务院关于印发《推动大规模设备更新和消费品以旧换新行动方案》的通知",
    "文章类型": "policy",
    "发文字号": "国发〔2024〕7号",
    "段落": [{"内容": "现将《推动大规模设备更新和消费品以旧换新行动方案》印发给你们。"}],
})
check("merge 把 发文字号 归一为 文号", a.get("文号") == "国发〔2024〕7号", str(a.get("文号")))
check("merge 后渲染器可见", source(a)["doc_number"] == "国发〔2024〕7号", source(a)["doc_number"])

# 4) 文号优先级：已归一的 文号 优先于原始字段
s = source({
    "文章标题": "某政策通知",
    "文章类型": "policy",
    "文号": "粤府〔2026〕1号",
    "发文字号": "不应覆盖",
})
check("文号 优先", s["doc_number"] == "粤府〔2026〕1号", s["doc_number"])

# 5) policyFiles 兜底仍工作：文章无文号时从 writtenText 回填
article = {"文章标题": "某政策通知", "段落": [{"内容": "正文。"}]}
r.attach_doc_numbers([article], {"content": {"data": {"policyFiles": [
    {"title": "某政策通知", "writtenText": "粤府〔2026〕2号"}
]}}})
check("policyFiles 兜底回填", article.get("文号") == "粤府〔2026〕2号", str(article.get("文号")))
check("兜底后渲染器可见", source(article)["doc_number"] == "粤府〔2026〕2号", source(article)["doc_number"])

print(f"\n结果：{passed} 通过，{failed} 失败")
raise SystemExit(0 if failed == 0 else 1)
