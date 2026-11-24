#!/usr/bin/env python3
"""1.8.2 两轨验收：Agent 轨解析、证据校验、两轨合流与报告呈现。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import render_trace_html as R  # noqa: E402

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


def make_sources():
    return [{
        "id": "1", "title": "示例材料", "agency": "示例机关", "data_source": "",
        "issuer": "示例机关", "is_policy": True, "date": "2025-11",
        "url": "https://example.gov.cn/a.html", "snapshot": "", "excerpt": "示例条款原文",
        "section": "", "kind": "policy", "type_key": "policy",
        "type_css": "pol", "has_link": True, "used": True, "citable": True,
        "claim_review": [], "search_key": "示例组", "channel": "示例通道",
    }]


def verify(check_raw, answer="结论[1]。", sources=None, config=None):
    payload = {"selfCheck": check_raw} if check_raw is not None else {}
    old = R.CONFIG
    if config:
        R.CONFIG = R._deep_merge(R.DEFAULT_CONFIG, config)
    try:
        v = R.compute_verification(answer, sources or make_sources(), payload)
        html = R.render_verify_panel(v)
    finally:
        R.CONFIG = old
    return v, html


def main():
    print("== 证据要素识别 ==")
    for text, expect, name in [
        ("引用材料[10]", True, "材料编号"),
        ("沪府规〔2025〕8号第五条", True, "文号+条款"),
        ("自2025-07-01起执行", True, "日期"),
        ("2023年度办法", True, "年份"),
        ("答案见 dknowc_search_answer.txt", True, "文件名"),
        ("按 GB 50011 执行", True, "标准号"),
        ("见附件", False, "无要素"),
        ("已核对，确认无误", False, "空话"),
    ]:
        check(f"证据要素-{name}", R.has_checkable_element(text) == expect, text)

    print("== 旧写法（1.8.1 兼容） ==")
    v, _ = verify({"fact_basis": "通过：逐条核对（沪府规〔2025〕8号第五条）",
                   "binding": "通过：已核对", "consistency": "通过：同一文件",
                   "freshness": "通过：2025-11 发布", "no_gap": "通过：无"})
    items = v["self_check"]["items"]
    check("旧写法-含文号判有据", items["事实有据"]["status"] == "pass", items["事实有据"])
    check("旧写法-无要素判证据不足", items["角标绑定"]["status"] == "evidence_missing", items["角标绑定"])
    check("旧写法-证据不足不判红", v["self_check"]["status"] == "pass", v["self_check"]["status"])
    check("旧写法-有据计数", v["agent_track"]["passed"] == 2, v["agent_track"])
    check("旧写法-证据不足清单", "角标绑定" in v["agent_track"]["evidence_missing"], v["agent_track"])

    print("== 结构化写法 ==")
    v, _ = verify({
        "fact_basis": {"verdict": "pass", "basis": "逐条核对适用对象",
                       "evidence": ["[10] 沪府规〔2025〕8号第五条"]},
        "binding": {"verdict": "pass", "basis": "抽查角标", "evidence": ["[1]"]},
    })
    check("结构化-有证据判通过",
          v["self_check"]["items"]["事实有据"]["status"] == "pass")
    check("结构化-总数只算白名单键", v["self_check"]["total"] == 2, v["self_check"]["total"])

    v, _ = verify({"fact_basis": {"verdict": "pass", "basis": "已核对"}})
    check("结构化-无证据判证据不足",
          v["self_check"]["items"]["事实有据"]["status"] == "evidence_missing")

    v, _ = verify({"fact_basis": {"verdict": "pass", "basis": "已核对", "evidence": ["见附件"]}})
    check("结构化-证据无要素判不足",
          v["self_check"]["items"]["事实有据"]["status"] == "evidence_missing")

    v, _ = verify({"fact_basis": {"verdict": "fail", "basis": "材料未覆盖"}})
    check("结构化-fail 整体未通过", v["overall"]["passed"] is False, v["overall"])
    check("结构化-fail 计入失败项", v["self_check"]["failed"] == 1, v["self_check"])

    v, _ = verify({"fact_basis": {"verdict": "pending", "basis": "待复核"}})
    check("结构化-pending 不否决", v["overall"]["passed"] is True, v["overall"])
    check("结构化-pending 计入待复核", v["agent_track"]["pending"] == 1, v["agent_track"])

    print("== 配置开关与别名 ==")
    v, _ = verify({"fact_basis": {"verdict": "pass", "basis": "已核对"}},
                  config={"agent_track": {"enabled": True, "require_evidence": False}})
    check("关证据要求-无证据也算通过",
          v["self_check"]["items"]["事实有据"]["status"] == "pass")

    payload = {"agentCheck": {"fact_basis": "通过：沪府规〔2025〕8号第五条"}}
    v = R.compute_verification("结论[1]。", make_sources(), payload)
    check("agentCheck 别名生效", v["self_check"]["items"]["事实有据"]["status"] == "pass", v.get("self_check"))

    print("== 两轨分工（脚本只判结构）==")
    payload = {"selfCheck": {"fact_basis": "通过：沪府规〔2025〕8号第五条"}}
    v = R.compute_verification("结论[1]。", make_sources(), payload)
    check("结构全绿即可通过", v["overall"]["passed"] is True, v["overall"])
    check("结果不含内容判断键", not any(k in v for k in ("hints", "claim_audit", "audit")), sorted(v))
    check("结果不含内容失败原因", not any("未定位" in r for r in v["overall"].get("reasons", [])), v["overall"])
    check("来源不带内容复核结论", "claim_review" not in make_sources()[0] or
          make_sources()[0].get("claim_review") == [])

    print("== 结构否决 ==")
    nosrc_excerpt = [dict(make_sources()[0], excerpt="")]
    v = R.compute_verification("结论[1]。", nosrc_excerpt,
                               {"selfCheck": {"fact_basis": "通过：沪府规〔2025〕8号第五条"}})
    check("缺摘录-结构不过", v["overall"]["passed"] is False, v["overall"])
    check("缺摘录-计入未通过依据", v["traceability"]["passed"] == 0, v["traceability"])

    bad_cite = [dict(make_sources()[0], citable=False)]
    v = R.compute_verification("结论[1]。", bad_cite,
                               {"selfCheck": {"fact_basis": "通过：沪府规〔2025〕8号第五条"}})
    check("不可引用-结构不过", v["overall"]["passed"] is False, v["overall"])

    v = R.compute_verification("结论[1]。", make_sources(),
                               {"selfCheck": {"fact_basis": {"verdict": "pass", "basis": "已核对"}}})
    check("证据不足-结构不过", v["overall"]["passed"] is False, v["overall"])

    print("== 官方外部信源 ==")
    check("官方-政府域名", R.is_official_external("https://zjj.sz.gov.cn/a.html"))
    check("官方-香港法定机构", R.is_official_external("https://www.mpfa.org.hk/tc/", "积金局"))
    # 1.8.2 实测：MPF 题里发布机构占位为"公开网站"，积金局官网整页被判非官方 → 补域名白名单
    check("官方-法定机构自有域名（发布机构占位）",
          R.is_official_external("https://mpfa.org.hk/mpf-system/mandatory-contributions", "公开网站", "強制性供款 - 僱員（積金局）"))
    check("官方-机构名带括号", R.is_official_external("https://example.com/a", "", "強制性供款（積金局）"))
    check("非官方-媒体转述积金局", not R.is_official_external(
        "https://finance.mingpao.com/fin/instantf/20260308/x", "公开网站",
        "積金局：持份者團體普遍認同上調MPF供款入息上下限（明報財經）"))
    check("官方-立法会", R.is_official_external("https://www.legco.gov.hk/a", "立法會"))
    check("非官方-商业媒体", not R.is_official_external("https://www.cet.com.cn/a.shtml", "中国经济网"))
    # 1.8.2 审核观察②：标题判官方去掉「局/厅/署」单字后缀（发布机构字段保留全表）
    check("标题-单字局后缀不判官方", not R.is_official_external("https://media.example/a", "公开网站", "XX税务局通报重要提示"))
    check("发布机构-局后缀仍判官方", R.is_official_external("https://gov.example/a", "浙江省杭州市人力社保局", ""))
    check("标题-多字机关词仍判官方", R.is_official_external("https://gov.example/b", "", "市监总局发布公告"))
    src = dict(make_sources()[0], unofficial=True, url="https://www.mpfa.org.hk/tc/", issuer="积金局")
    norm = R.extract_sources({"materials": [{
        "编号": 1, "标题": "僱員 - 積金局", "源网址": "https://www.mpfa.org.hk/tc/",
        "发布机构": "积金局", "原文": "供款5%", "来源性质": "unofficial", "素材类型": "policy"
    }]}, snapshot_enabled=False)[0]
    check("外部官方信源降级为非非官方", norm["official_external"] is True and norm["unofficial"] is False, norm)

    # 1.8.2：材料类型不再展示（接口 类型 与文体常年不符）；仅保留有事实依据的来源性质徽标
    third = R.extract_sources({"materials": [{
        "编号": 1, "标题": "社保计算器", "源网址": "https://aifincalc.com/city/hangzhou/",
        "原文": "灵活就业医保固定月缴486.59元", "类型": "policy", "来源性质": "unofficial"
    }]}, snapshot_enabled=False)[0]
    check("第三方材料仍标非官方来源", third["unofficial"] is True)
    check("核验结果不再含材料构成", "coverage" not in
          R.compute_verification("结论[1]。", make_sources(),
                                 {"selfCheck": {"fact_basis": "通过：沪府规〔2025〕8号第五条"}}))

    print("== 措辞替换单遍（审核观察①） ==")
    R.apply_config(None)
    check("无级联-宿主WebSearch", R.user_facing_text("宿主 WebSearch 检索") == "公开网络检索 检索",
          R.user_facing_text("宿主 WebSearch 检索"))
    check("无级联-公开网络不再二次替换", "检索来源检索" not in R.user_facing_text("宿主 WebSearch"))

    print("== 渲染链路不接内容检查库 ==")
    src = Path(R.__file__).read_text(encoding="utf-8")
    check("渲染器不导入 claim_audit", "claim_audit" not in src or "import claim_audit" not in src)
    check("渲染器不调用 audit_answer", "audit_answer(" not in src)
    check("渲染器不采信内容核验字段", "引用核验通过" not in src and "claim_verified" not in src
          and "claim_review" not in src)

    print("== 报告呈现 ==")
    v, html = verify({"fact_basis": "通过：沪府规〔2025〕8号第五条", "binding": "通过：抽查 [1] 已绑定"})
    check("渲染-结构核验标签", "结构核验" in html)
    check("渲染-AI 验收标签", "AI 验收" in html)
    check("渲染-有据计数", "AI 验收 2/2 有据" in html, html[:400])
    check("渲染-两轨合流说明", "任一轨不过" in html)
    check("渲染-不显示材料构成", "材料构成" not in html, html[:400])
    check("渲染-卡片无类型标签", 'class="sc-type"' not in html)
    check("渲染-结构核验仅三项", "依据溯源 / 引用对应 / 材料新旧" in html)

    v, html = verify({"fact_basis": "通过：已核对"})
    check("渲染-证据不足点名", "证据不足" in html)
    check("渲染-明细折叠", "查看 AI 验收明细" in html)

    v, html = verify({"fact_basis": {"verdict": "fail", "basis": "材料未覆盖"}})
    check("渲染-失败行", "✗ AI 验收 0/1" in html, html[:300])

    v, html = verify(None)
    check("渲染-未记录", "AI 验收 未记录" in html)

    print(f"\n结果：{passed} 通过，{failed} 失败")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
