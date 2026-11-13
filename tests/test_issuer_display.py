#!/usr/bin/env python3
"""来源卡“发文机构/来源”展示口径回归测试（1.7.3：V2/V3）。

规则：只显示接口返回的发文机构；政策缺失显示“发文机构待补”，非政策缺失显示
“公开网站”；任何类型都不显示“数据源”网站名；不从标题推导发文机构。
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


# 1) V2 政策：发文机构优先，不显示数据源
s = source({
    "文章标题": "广州住房公积金管理中心关于2026年度住房公积金缴存调整有关问题的通知",
    "文章类型": "policy",
    "发布日期可信度": "高",
    "发布或实施机构": "广州住房公积金管理中心##",
    "数据源": "中国房地产业协会门户网站",
})
check("V2 policy 显示发文机构", s["agency"] == "广州住房公积金管理中心", s["agency"])
check("原始数据源字段仍保留", s["data_source"] == "中国房地产业协会门户网站")

# 2) 深度搜索政策：国务院优先于郑州市门户网站
s = source({
    "文章标题": "住房公积金管理条例",
    "文章类型": "policy",
    "发布日期可信度": "高",
    "发布或实施机构": "国务院",
    "数据源": "郑州市人民政府门户网站",
})
check("deep policy 显示国务院", s["agency"] == "国务院", s["agency"])

# 2.1) V2 多机构串：每个机构后的 ## 都要清掉，不能只清首尾
s = source({
    "文章标题": "广东省创业担保贷款实施办法",
    "文章类型": "policy",
    "发布日期可信度": "高",
    "发布或实施机构": "广东省人力资源和社会保障厅##、中国人民银行广东省分行##、广东省财政厅##",
})
check("多机构串内部 ## 全部清除",
      s["agency"] == "广东省人力资源和社会保障厅、中国人民银行广东省分行、广东省财政厅",
      s["agency"])
check("展示机构不含 #", "#" not in s["agency"], s["agency"])

# 2.2) merge 透传：接口返回的机构字段不能被白名单丢掉
a = m._to_article({
    "文章标题": "广东省创业担保贷款实施办法",
    "文章类型": "policy",
    "发布或实施机构": "广东省人力资源和社会保障厅##",
    "数据源": "某县人民政府门户网站",
    "段落": [{"内容": "第一条 为支持创业带动就业……"}],
})
s = source(a)
check("merge 保留发布或实施机构", a.get("发布或实施机构") == "广东省人力资源和社会保障厅##", str(a.get("发布或实施机构")))
check("merge 后展示真实机构", s["agency"] == "广东省人力资源和社会保障厅", s["agency"])
check("merge 后仍不展示数据源", s["agency"] != s["data_source"] and s["data_source"] == "某县人民政府门户网站", str(s))

# 3) govSite/新闻：不显示数据源，显示公开网站
s = source({
    "文章标题": "各地积极优化住房公积金政策",
    "文章类型": "govSite",
    "发布日期可信度": "较高",
    "数据源": "住房和城乡建设部门户网站",
})
check("govSite 不显示数据源", s["agency"] == "公开网站", s["agency"])

# 4) 仅 sourceElement 的站点名不能当发文机构
for site in ("中国经济网", "新华网", "中国政府网"):
    s = source({"文章标题": "多地优化住房公积金政策", "文章类型": "govSite", "发布日期可信度": "较高", "sourceElement": site})
    check(f"sourceElement 站点名被隐藏：{site}", s["agency"] == "公开网站", s["agency"])

# 5) unit 数组逐元素清理 ##，并跳过 None
s = source({"文章标题": "关于做好某项工作的通知", "文章类型": "policy", "发布日期可信度": "高", "unit": ["##财政部##", "##国家税务总局##"]})
check("unit 数组逐元素去 ##", s["agency"] == "财政部、国家税务总局", s["agency"])
s = source({"文章标题": "关于做好某项工作的通知", "文章类型": "policy", "发布日期可信度": "高", "unit": [None, "财政部"]})
check("unit 跳过 None", s["agency"] == "财政部", s["agency"])

# 6) 政策缺机构：显示待补，不从标题推导
s = source({
    "文章标题": "财政部关于做好某项工作的通知",
    "文章类型": "policy",
    "发布日期可信度": "高",
    "数据源": "某门户网站",
})
check("政策缺机构不推导标题", s["agency"] == "发文机构待补", s["agency"])

# 7) 非政策缺机构：显示公开网站
s = source({
    "文章标题": "各地积极优化住房公积金政策",
    "文章类型": "govSite",
    "发布日期可信度": "较高",
    "数据源": "住房和城乡建设部门户网站",
})
check("非政策缺机构显示公开网站", s["agency"] == "公开网站", s["agency"])

# 8) 高可信新闻不能当政策：显示公开网站
s = source({
    "文章标题": "住房公积金改革新政：提取范围扩大，覆盖人群突破",
    "发布日期可信度": "高",
    "数据源": "中国经济网门户网站",
})
check("高可信新闻不判政策", s["is_policy"] is False, str(s["is_policy"]))
check("高可信新闻显示公开网站", s["agency"] == "公开网站", s["agency"])

# 9) policy_news 不能因包含 policy 被判成政策
s = source({
    "文章标题": "多地优化住房公积金政策",
    "文章类型": "policy_news",
    "发布日期可信度": "高",
    "数据源": "中国经济网门户网站",
})
check("policy_news 不判政策", s["is_policy"] is False, str(s["is_policy"]))
check("policy_news 显示公开网站", s["agency"] == "公开网站", s["agency"])

print(f"\n结果：{passed} 通过，{failed} 失败")
raise SystemExit(0 if failed == 0 else 1)
