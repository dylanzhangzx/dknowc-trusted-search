#!/usr/bin/env python3
"""1.8.0 报告引用形态：正文只留可点击 [n]，点击弹引用依据弹窗；专库未引用材料折叠。"""

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


def make_article(cid, title, used=True):
    art = {
        "编号": cid,
        "文章标题": title,
        "文章类型": "policy",
        "检索通道": "深知可信搜索",
        "搜索条件": "本次检索",
        "段落": [{"id": 1, "内容": f"{title}正文摘录内容，用于核验。"}],
    }
    if not used:
        art["已引用"] = False
    return art


def main():
    articles = [make_article(1, "职工带薪年休假条例"), make_article(2, "劳动法"),
                make_article(3, "未引用的参考材料", used=False)]
    payload = {"content": {"data": {"检索文章": articles}}}
    answer = "职工连续工作1年以上的享受年休假[1]，工资照发[2]。"
    html = rt.render_html(payload, "测试报告", answer_override=answer)

    check("正文角标是可点击引用链接", 'class="cite-link"' in html and 'data-cite="1"' in html)
    check("正文角标保留数字形态", ">[1]</a>" in html)
    check("不再内联引文胶囊", 'class="jb"' not in html)
    check("引用依据弹窗存在", 'class="cite-modal"' in html and 'class="cite-mask"' in html)
    check("弹窗有关闭按钮", "cite-modal-close" in html)
    check("弹窗由角标触发", "openCite(" in html)
    check("打印模式隐藏弹层", ".cite-mask,.cite-modal,.progress" in html)
    check("专库未引用材料折叠区", 'class="lib-unused"' in html)
    check("折叠区标注未参与结论", "未参与答案结论" in html)

    print(f"\n结果：{passed} 通过，{failed} 失败")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
