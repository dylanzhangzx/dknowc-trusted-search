#!/usr/bin/env python3
"""1.8.0 参考卡表格完整性：表格必须完整保留，不能按普通摘要截断。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import render_trace_html as rt  # noqa: E402

passed = 0
failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ok   {name}")
    else:
        failed += 1
        print(f"  FAIL {name} {detail}")


def main():
    rows = "".join(f"<tr><td>项目{i}</td><td>{i}万元</td></tr>" for i in range(1, 21))
    text = f"<table><thead><tr><th>项目</th><th>金额</th></tr></thead><tbody>{rows}</tbody></table>"
    item = {"文章标题": "表格材料", "文章类型": "policy", "段落": [{"id": 1, "内容": text}]}
    source = rt.source_from_article(item, 1)
    source["used"] = True
    source["claim_verified"] = True
    html = rt.render_source_card(source)
    check("表格 20 行全部保留", all(f"项目{i}" in html for i in range(1, 21)))
    check("表头保留", "金额" in html)
    check("表格未被摘要截断", "项目20" in html and "20万元" in html)

    nested = ("<table><thead><tr><th>序号</th><th>明细</th></tr>"
              "<tr><th>1</th><th>2</th></tr></thead><tbody>"
              "<tr><td>1</td><td><table><tr><td>内层</td></tr></table></td></tr>"
              "</tbody></table>")
    cleaned = rt.sanitize_table_html(nested)
    check("嵌套表不被重建错位", cleaned.count("<table") == 2 and "<td><table" in cleaned)
    check("嵌套表保留 colspan/rowspan 之外的结构", "内层" in cleaned)

    print(f"\n结果：{passed} 通过，{failed} 失败")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
