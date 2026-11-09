#!/usr/bin/env python3
"""websearch_convert.py 单元测试 + merge 联调（1.7.2）。

不依赖 pytest：纯 Python + check()，失败即以非零码退出。
覆盖：多宿主输入包装、cited_text 回填、无摘录丢弃、字段别名、URL 校验/归一/去重、
模板行过滤、段落切分、上限截断、退出码、merge 权威优先与外部标记透传。

用法：python3 tests/test_websearch_convert.py
"""

import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
RESULTS = SKILL / "official-docs" / "search-results"
sys.path.insert(0, str(SCRIPTS))

import websearch_convert as wc  # noqa: E402
import render_trace_html as rt  # noqa: E402

PASSED = 0
FAILED = 0


def check(name: str, cond: bool, detail: str = ""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  ✓ {name}")
    else:
        FAILED += 1
        print(f"  ✗ {name}" + (f" — {detail}" if detail else ""))


def articles(payload, **kwargs):
    return wc.convert(payload, **kwargs)["content"]["data"]["检索文章"]


def run_cli(args, stdin_text=None):
    proc = subprocess.run([sys.executable, str(SCRIPTS / "websearch_convert.py")] + args,
                          input=stdin_text, text=True, capture_output=True)
    return proc.returncode, proc.stdout + proc.stderr


def main():
    print("== 基础转换 ==")
    payload = {
        "query": "邮轮赴日签证",
        "results": [
            {"title": "日本允许邮轮旅客免签入境", "url": "https://example.gov.cn/a?utm_source=x#top",
             "content": "寄港地上陆许可：允许邮轮旅客临时上岸，期限不超过72小时，需随船返回。",
             "published_at": "2015-03-16", "source": "上海边检"},
            {"title": "只有标题和链接", "url": "https://example.com/empty"},
            {"title": "非法协议", "url": "javascript:alert(1)", "content": "x"},
        ],
    }
    arts = articles(payload)
    check("只保留有摘录的条目", len(arts) == 1, f"got {len(arts)}")
    a = arts[0] if arts else {}
    check("URL 去 tracking/fragment", a.get("源网址") == "https://example.gov.cn/a", a.get("源网址", ""))
    check("检索通道=宿主 WebSearch", a.get("检索通道") == "宿主 WebSearch")
    check("非官方来源/非权威（不再叠加待核验）", a.get("非官方来源") is True
          and "待核验" not in a and a.get("数据权威性") == "非权威")
    check("发布日期保留", a.get("发布日期") == "2015-03-16")
    check("数据源保留", a.get("数据源") == "上海边检")
    check("正文未被“返回”模板词误杀", "需随船返回" in (a.get("段落") or [{}])[0].get("内容", ""))
    check("转换器拒绝带 userinfo 的 URL",
          len(articles({"results": [{"title": "带凭据", "url": "https://user:pass@example.com/a",
                                     "content": "正文"}]})) == 0)
    check("渲染层 _safe_url 拒绝 userinfo",
          rt._safe_url("https://user:pass@example.com/a") == "")

    print("== 宿主包装兼容 ==")
    for name, p in [
        ("裸数组", [{"name": "标题A", "link": "https://a.example/1", "snippet": "正文A"}]),
        ("results", {"results": [{"title": "标题B", "url": "https://b.example/1", "snippet": "正文B"}]}),
        ("items", {"items": [{"title": "标题C", "url": "https://c.example/1", "summary": "正文C"}]}),
        ("webPages.value", {"webPages": {"value": [{"name": "标题D", "link": "https://d.example/1", "snippet": "正文D"}]}}),
        ("organic_results", {"organic_results": [{"title": "标题E", "link": "https://e.example/1", "snippet": "正文E"}]}),
        ("output[].results", {"output": [{"results": [{"title": "标题F", "link": "https://f.example/1", "snippet": "正文F"}]}]}),
    ]:
        got = articles(p)
        check(f"{name} → 1 篇", len(got) == 1, f"got {len(got)}")
        if got:
            check(f"{name} 标题映射", got[0]["文章标题"] in ("标题A", "标题B", "标题C", "标题D", "标题E", "标题F"))

    print("== Anthropic web_search_result + cited_text ==")
    anthropic = {"content": [
        {"type": "web_search_result", "url": "https://go.jp/example", "title": "日本入管法",
         "encrypted_content": "xxx"},
        {"type": "text", "text": "依据……", "citations": [
            {"type": "web_search_result_location", "url": "https://go.jp/example",
             "title": "日本入管法", "cited_text": "第14条之2 寄港地上陆许可。"}]},
    ]}
    got = articles(anthropic)
    check("cited_text 回填正文", len(got) == 1 and got[0]["段落"][0]["内容"] == "第14条之2 寄港地上陆许可。")

    print("== 无摘录丢弃 / 字段别名 / 日期 ==")
    got = articles({"results": [
        {"name": "别名", "link": "https://x.example/1", "text": "别名正文", "date": "2026-01-02"},
        {"title": "无正文", "url": "https://x.example/2"},
    ]})
    check("别名映射 + 无摘录丢弃", len(got) == 1 and got[0]["文章标题"] == "别名"
          and got[0]["发布日期"] == "2026-01-02")

    print("== URL 去重 ==")
    got = articles({"results": [
        {"title": "同文", "url": "https://x.example/1?utm_source=a#top", "content": "第一段"},
        {"title": "同文", "url": "https://x.example/1/", "content": "第二段"},
    ]})
    check("同 URL 归一后只留 1 篇", len(got) == 1, f"got {len(got)}")

    print("== 模板行/HTML 清洗 ==")
    got = articles({"results": [{"title": "清洗", "url": "https://x.example/1",
                                 "content": "<p>首页</p><p>正文一二三</p><script>alert(1)</script><p>第二段</p>"}]})
    texts = [p["内容"] for p in got[0]["段落"]]
    check("导航词整行被过滤", "首页" not in texts, str(texts))
    check("正文保留", "正文一二三" in texts and "第二段" in texts, str(texts))
    check("script 不泄漏", all("<script" not in t for t in texts))

    print("== 长文切分 / 上限 ==")
    long_text = "第一段。" * 800
    got = articles({"results": [{"title": "长文", "url": "https://x.example/1", "content": long_text}]},
                   max_chars=20000)
    check("长文切成多段", len(got[0]["段落"]) > 1, f"got {len(got[0]['段落'])}")
    check("单段不超上限", all(len(p["内容"]) <= wc.MAX_SEGMENT_CHARS for p in got[0]["段落"]))
    got = articles({"results": [{"title": "截断", "url": "https://x.example/1", "content": "字" * 500}]},
                   max_chars=200)
    check("正文总量截断", len("".join(p["内容"] for p in got[0]["段落"])) <= 200)
    got = articles({"results": [
        {"title": f"第{i}篇", "url": f"https://x.example/{i}", "content": "正文"} for i in range(5)
    ]}, max_results=2)
    check("条数上限生效", len(got) == 2, f"got {len(got)}")

    print("== 退出码 ==")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        empty = td / "empty.json"
        empty.write_text(json.dumps({"results": [{"title": "x", "url": "https://x.example/1"}]}), encoding="utf-8")
        bad = td / "bad.json"
        bad.write_text("not-json", encoding="utf-8")
        code, out = run_cli([str(empty), "-o", "test_ws_empty.json"])
        check("无结果 exit 3", code == 3, out)
        code, out = run_cli([str(empty), "-o", "test_ws_empty.json", "--allow-empty"])
        check("--allow-empty exit 0", code == 0, out)
        code, out = run_cli([str(bad), "-o", "test_ws_bad.json"])
        check("坏 JSON exit 1", code == 1, out)
        code, out = run_cli([str(empty), "-o", "/tmp/outside.json"])
        check("输出越界 exit 2", code == 2, out)

    print("== merge 联调：权威优先 + 待核验 ==")
    def write(name, data):
        (RESULTS / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def merged(inputs):
        out = f"test_ws_merged_{uuid.uuid4().hex[:8]}.json"
        args = [sys.executable, str(SCRIPTS / "merge_search_results.py"), "-o", out]
        for path, key in inputs:
            args += ["--input", path, "--search-key", key]
        proc = subprocess.run(args, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stdout + proc.stderr)
        return json.loads((RESULTS / out).read_text(encoding="utf-8"))

    try:
        official = {"content": {"data": {"检索文章": [{
            "文章标题": "日本邮轮免签政策", "源网址": "https://example.gov.cn/a",
            "数据源": "官网", "数据权威性": "权威", "检索通道": "深知可信搜索",
            "段落": [{"id": 1, "内容": "官方原文段落。"}]}], "policyFiles": []}}}
        external = {"content": {"data": {"检索文章": [{
            "文章标题": "日本邮轮免签政策", "源网址": "https://example.gov.cn/a/?utm_source=x",
            "数据源": "外部站", "数据权威性": "非权威", "非官方来源": True, "待核验": True,
            "检索通道": "宿主 WebSearch", "段落": [{"id": 1, "内容": "外部补充段落。"}]}], "policyFiles": []}}}
        write("test_ws_official.json", official)
        write("test_ws_external.json", external)
        d = merged([("test_ws_official.json", "库内"), ("test_ws_external.json", "公开资料补充")])
        arts = d["content"]["data"]["检索文章"]
        a = arts[0]
        check("同 URL 合并为 1 篇", len(arts) == 1, f"got {len(arts)}")
        check("官方材料不被标非官方", not a.get("非官方来源") and not a.get("待核验"), str(a))
        check("外部段落不混入官方卡", [p["内容"] for p in a["段落"]] == ["官方原文段落。"], str(a["段落"]))

        stage2 = {"content": {"data": {"检索文章": [{
            "文章标题": "日本邮轮免签政策", "源网址": "https://example.gov.cn/a",
            "数据源": "官网", "数据权威性": "权威", "非官方来源": True,
            "检索通道": "深知可信搜索·联网", "段落": [{"id": 1, "内容": "联网原段。"}]}], "policyFiles": []}}}
        stage3 = {"content": {"data": {"检索文章": [{
            "文章标题": "日本邮轮免签政策", "源网址": "https://example.gov.cn/a/",
            "数据源": "外部站", "数据权威性": "非权威", "非官方来源": True, "待核验": True,
            "检索通道": "宿主 WebSearch", "段落": [{"id": 1, "内容": "外部补充段。"}]}], "policyFiles": []}}}
        write("test_ws_stage2.json", stage2)
        write("test_ws_stage3.json", stage3)
        d = merged([("test_ws_stage2.json", "可信联网"), ("test_ws_stage3.json", "公开资料补充")])
        a = d["content"]["data"]["检索文章"][0]
        check("阶段二+三同 URL 保留待核验", a.get("待核验") is True, str(a))
        check("阶段二+三段落并集", len(a.get("段落") or []) == 2, str(a.get("段落")))
        check("双通道保留", "宿主 WebSearch" in (a.get("检索通道") or ""), a.get("检索通道", ""))

        # 阻塞项 1 回归：库内条目没有 数据权威性 时，不能被外部同 URL 的“非权威”污染
        official_noauth = {"content": {"data": {"检索文章": [{
            "文章标题": "无权威字段官方文", "源网址": "https://example.gov.cn/noauth",
            "数据源": "官网", "检索通道": "深知可信搜索",
            "段落": [{"id": 1, "内容": "官方原文段落。"}]}], "policyFiles": []}}}
        external_noauth = {"content": {"data": {"检索文章": [{
            "文章标题": "无权威字段官方文", "源网址": "https://example.gov.cn/noauth?utm_source=x",
            "数据源": "外部站", "数据权威性": "非权威", "非官方来源": True,
            "检索通道": "宿主 WebSearch", "段落": [{"id": 1, "内容": "外部补充段落。"}]}], "policyFiles": []}}}
        write("test_ws_official_noauth.json", official_noauth)
        write("test_ws_external_noauth.json", external_noauth)
        d = merged([("test_ws_official_noauth.json", "库内"),
                    ("test_ws_external_noauth.json", "公开资料补充")])
        a = d["content"]["data"]["检索文章"][0]
        check("库内无权威字段不被外部非权威污染", "数据权威性" not in a, str(a))
        check("库内无权威字段不被标非官方", not a.get("非官方来源") and not a.get("待核验"), str(a))
        check("库内优先：数据源/段落/通道/分组均为库内",
              a.get("数据源") == "官网"
              and [p["内容"] for p in a.get("段落") or []] == ["官方原文段落。"]
              and a.get("检索通道") == "深知可信搜索"
              and a.get("搜索条件") == "库内", str(a))
        # 反向输入顺序（外部在前）也必须让官方记录整体胜出，与顺序无关
        d_rev = merged([("test_ws_external_noauth.json", "公开资料补充"),
                        ("test_ws_official_noauth.json", "库内")])
        a_rev = d_rev["content"]["data"]["检索文章"][0]
        check("反向顺序也不被外部非权威污染",
              "数据权威性" not in a_rev and not a_rev.get("非官方来源"), str(a_rev))
        check("反向顺序仍为库内数据源/段落/通道/分组",
              a_rev.get("数据源") == "官网"
              and [p["内容"] for p in a_rev.get("段落") or []] == ["官方原文段落。"]
              and a_rev.get("检索通道") == "深知可信搜索"
              and a_rev.get("搜索条件") == "库内", str(a_rev))

        # 重要项：官方缺字段时，外部同 URL 的数据源/日期/文号/快照不得补进官方卡
        official_sparse = {"content": {"data": {"检索文章": [{
            "文章标题": "官方缺字段文", "源网址": "https://example.gov.cn/sparse",
            "检索通道": "深知可信搜索", "段落": [{"id": 1, "内容": "官方段。"}]}], "policyFiles": []}}}
        external_full = {"content": {"data": {"检索文章": [{
            "文章标题": "官方缺字段文", "源网址": "https://example.gov.cn/sparse?utm_source=x",
            "数据源": "外部站", "发布日期": "2026-01-01", "文号": "外部文号",
            "screenShotPath": "https://example.com/snap", "非官方来源": True,
            "检索通道": "宿主 WebSearch", "段落": [{"id": 1, "内容": "外部段。"}],
            "搜索条件": "公开资料补充"}], "policyFiles": []}}}
        write("test_ws_sparse_official.json", official_sparse)
        write("test_ws_full_external.json", external_full)
        d_sparse = merged([("test_ws_full_external.json", "公开资料补充"),
                           ("test_ws_sparse_official.json", "库内")])
        a_sparse = d_sparse["content"]["data"]["检索文章"][0]
        check("官方缺字段不被外部元数据补齐",
              a_sparse.get("数据源") in (None, "")
              and a_sparse.get("发布日期") in (None, "")
              and a_sparse.get("文号") in (None, "")
              and a_sparse.get("screenShotPath") in (None, "")
              and [p["内容"] for p in a_sparse.get("段落") or []] == ["官方段。"], str(a_sparse))

        # 近似重复（不同 URL、句子指纹相同）也遵守官方整体胜出
        dup_sents = [
            "这是第一句用于测试近似重复的官方内容。",
            "这是第二句用于测试近似重复的官方内容。",
            "这是第三句用于测试近似重复的官方内容。",
            "这是第四句用于测试近似重复的官方内容。",
        ]
        official_dup = {"content": {"data": {"检索文章": [{
            "文章标题": "近似重复官方文", "源网址": "https://example.gov.cn/dup-official",
            "数据源": "官网", "检索通道": "深知可信搜索",
            "段落": [{"id": i, "内容": s} for i, s in enumerate(dup_sents, 1)]}], "policyFiles": []}}}
        external_dup = {"content": {"data": {"检索文章": [{
            "文章标题": "近似重复外部文", "源网址": "https://example.com/dup-external",
            "数据源": "外部站", "数据权威性": "非权威", "非官方来源": True,
            "检索通道": "宿主 WebSearch",
            "段落": [{"id": i, "内容": s} for i, s in enumerate(dup_sents + ["这是外部额外添加的第五句内容。"], 1)]}],
            "policyFiles": []}}}
        write("test_ws_dup_official.json", official_dup)
        write("test_ws_dup_external.json", external_dup)
        d_dup = merged([("test_ws_dup_official.json", "库内"),
                        ("test_ws_dup_external.json", "公开资料补充")])
        a_dup = d_dup["content"]["data"]["检索文章"][0]
        check("近似重复官方整体胜出",
              a_dup.get("数据源") == "官网" and not a_dup.get("非官方来源")
              and len(a_dup.get("段落") or []) == 4, str(a_dup))

        # 三验重要项：过程条 new_articles 必须随官方胜出回滚，且与 --input 顺序无关
        official_calls = {"content": {"data": {"检索文章": [{
            "文章标题": "过程统计官方文", "源网址": "https://example.gov.cn/calls",
            "数据源": "官网", "检索通道": "深知可信搜索",
            "段落": [{"id": 1, "内容": "官方统计段。"}]}], "policyFiles": []}}}
        external_calls = {"content": {"data": {"检索文章": [
            {"文章标题": "过程统计官方文", "源网址": "https://example.gov.cn/calls?utm_source=x",
             "数据源": "外部站", "数据权威性": "非权威", "非官方来源": True,
             "检索通道": "宿主 WebSearch", "段落": [{"id": 1, "内容": "外部同文段。"}]},
            {"文章标题": "另一篇外部文", "源网址": "https://example.com/other",
             "数据源": "外部站", "数据权威性": "非权威", "非官方来源": True,
             "检索通道": "宿主 WebSearch", "段落": [{"id": 1, "内容": "另一篇外部段。"}]},
        ], "policyFiles": []}}}
        write("test_ws_calls_official.json", official_calls)
        write("test_ws_calls_external.json", external_calls)
        for _name, _order in (
            ("官方在前", [("test_ws_calls_official.json", "库内"),
                          ("test_ws_calls_external.json", "公开资料补充")]),
            ("外部在前", [("test_ws_calls_external.json", "公开资料补充"),
                          ("test_ws_calls_official.json", "库内")]),
        ):
            _d = merged(_order)
            _stats = {c["label"]: c for c in _d["search_meta"]["calls"]}
            check(f"过程统计顺序无关（{_name}）：库内新增 1 篇",
                  _stats["库内"]["new_articles"] == 1, str(_stats["库内"]))
            check(f"过程统计顺序无关（{_name}）：外部新增 1 篇（非 2 篇）",
                  _stats["公开资料补充"]["new_articles"] == 1, str(_stats["公开资料补充"]))
            check(f"过程统计顺序无关（{_name}）：最终 2 篇",
                  len(_d["content"]["data"]["检索文章"]) == 2,
                  f"got {len(_d['content']['data']['检索文章'])}")
            check(f"内部路次标记不进入产物（{_name}）",
                  all("_route_idx" not in a for a in _d["content"]["data"]["检索文章"]))

        # 近似重复丢弃外部卡时也回滚该路 new_articles
        for _name, _order in (
            ("官方在前", [("test_ws_dup_official.json", "库内"),
                          ("test_ws_dup_external.json", "公开资料补充")]),
            ("外部在前", [("test_ws_dup_external.json", "公开资料补充"),
                          ("test_ws_dup_official.json", "库内")]),
        ):
            _d = merged(_order)
            _stats = {c["label"]: c for c in _d["search_meta"]["calls"]}
            check(f"近似重复统计回滚（{_name}）",
                  _stats["库内"]["new_articles"] == 1
                  and _stats["公开资料补充"]["new_articles"] == 0,
                  str(_stats))

        # 四验重要项：官方整卡替换时，外部路此前补充的 added_paragraphs 也要回滚
        s2_contrib = {"content": {"data": {"检索文章": [{
            "文章标题": "补充段回滚文", "源网址": "https://example.gov.cn/contrib",
            "数据源": "联网", "非官方来源": True, "检索通道": "深知可信搜索·联网",
            "段落": [{"id": 1, "内容": "联网原段。"}]}], "policyFiles": []}}}
        s3_contrib = {"content": {"data": {"检索文章": [{
            "文章标题": "补充段回滚文", "源网址": "https://example.gov.cn/contrib?utm_source=x",
            "数据源": "外部站", "数据权威性": "非权威", "非官方来源": True,
            "检索通道": "宿主 WebSearch", "段落": [{"id": 1, "内容": "宿主补充段。"}]}],
            "policyFiles": []}}}
        official_contrib = {"content": {"data": {"检索文章": [{
            "文章标题": "补充段回滚文", "源网址": "https://example.gov.cn/contrib",
            "数据源": "官网", "检索通道": "深知可信搜索",
            "段落": [{"id": 1, "内容": "官方最终段。"}]}], "policyFiles": []}}}
        write("test_ws_contrib_s2.json", s2_contrib)
        write("test_ws_contrib_s3.json", s3_contrib)
        write("test_ws_contrib_official.json", official_contrib)
        for _name, _order in (
            ("外部路在前", [("test_ws_contrib_s2.json", "可信联网"),
                            ("test_ws_contrib_s3.json", "公开资料补充"),
                            ("test_ws_contrib_official.json", "库内")]),
            ("官方在前", [("test_ws_contrib_official.json", "库内"),
                          ("test_ws_contrib_s2.json", "可信联网"),
                          ("test_ws_contrib_s3.json", "公开资料补充")]),
        ):
            _d = merged(_order)
            _stats = {c["label"]: c for c in _d["search_meta"]["calls"]}
            _arts = _d["content"]["data"]["检索文章"]
            check(f"官方替换后补充段回滚（{_name}）：最终仅官方段",
                  len(_arts) == 1
                  and [p["内容"] for p in _arts[0].get("段落") or []] == ["官方最终段。"],
                  str(_arts))
            check(f"官方替换后补充段回滚（{_name}）：外部两路 新增/补段均为 0",
                  _stats["可信联网"]["new_articles"] == 0
                  and _stats["可信联网"]["added_paragraphs"] == 0
                  and _stats["公开资料补充"]["new_articles"] == 0
                  and _stats["公开资料补充"]["added_paragraphs"] == 0,
                  str(_stats))
            check(f"官方替换后补充段回滚（{_name}）：库内新增 1 篇",
                  _stats["库内"]["new_articles"] == 1, str(_stats["库内"]))

        # 近似重复丢弃“已吸收其他外部段落”的外部卡时，同样回滚新增与补段
        ext_dup_a = {"content": {"data": {"检索文章": [{
            "文章标题": "重复外部文", "源网址": "https://example.com/dup-contrib",
            "数据源": "外部站", "数据权威性": "非权威", "非官方来源": True,
            "检索通道": "宿主 WebSearch",
            "段落": [{"id": i, "内容": s} for i, s in enumerate(dup_sents, 1)]}],
            "policyFiles": []}}}
        ext_dup_b = {"content": {"data": {"检索文章": [{
            "文章标题": "重复外部文", "源网址": "https://example.com/dup-contrib",
            "数据源": "外部站", "数据权威性": "非权威", "非官方来源": True,
            "检索通道": "宿主 WebSearch",
            "段落": [{"id": i, "内容": s} for i, s in enumerate(
                dup_sents + ["这是另一路补充的额外段落内容。"], 1)]}],
            "policyFiles": []}}}
        official_dup2 = {"content": {"data": {"检索文章": [{
            "文章标题": "近似官方文", "源网址": "https://example.gov.cn/dup-contrib-official",
            "数据源": "官网", "检索通道": "深知可信搜索",
            "段落": [{"id": i, "内容": s} for i, s in enumerate(dup_sents, 1)]}],
            "policyFiles": []}}}
        write("test_ws_dup_contrib_a.json", ext_dup_a)
        write("test_ws_dup_contrib_b.json", ext_dup_b)
        write("test_ws_dup_contrib_official.json", official_dup2)
        for _name, _order in (
            ("外部在前", [("test_ws_dup_contrib_a.json", "可信联网"),
                          ("test_ws_dup_contrib_b.json", "公开资料补充"),
                          ("test_ws_dup_contrib_official.json", "库内")]),
            ("官方在前", [("test_ws_dup_contrib_official.json", "库内"),
                          ("test_ws_dup_contrib_a.json", "可信联网"),
                          ("test_ws_dup_contrib_b.json", "公开资料补充")]),
        ):
            _d = merged(_order)
            _stats = {c["label"]: c for c in _d["search_meta"]["calls"]}
            check(f"近似重复补段回滚（{_name}）：外部两路 0 新增 0 补段",
                  _stats["可信联网"]["new_articles"] == 0
                  and _stats["可信联网"]["added_paragraphs"] == 0
                  and _stats["公开资料补充"]["new_articles"] == 0
                  and _stats["公开资料补充"]["added_paragraphs"] == 0,
                  str(_stats))
            check(f"近似重复补段回滚（{_name}）：最终 1 篇官方文",
                  len(_d["content"]["data"]["检索文章"]) == 1
                  and _d["content"]["data"]["检索文章"][0].get("数据源") == "官网",
                  str(_d["content"]["data"]["检索文章"]))

        # 六验重要项：同权威近似重复丢弃卡也要回滚 new_articles；
        # 多个外部输入复用同一分组标签时，分组“新增”不得超过最终材料数。
        ab_sents = [
            "这是外部重复文的第一句测试内容。",
            "这是外部重复文的第二句测试内容。",
            "这是外部重复文的第三句测试内容。",
            "这是外部重复文的第四句测试内容。",
        ]
        ext_a = {"content": {"data": {"检索文章": [{
            "文章标题": "外部重复文A", "源网址": "https://example.com/ext-a",
            "数据源": "外部站", "数据权威性": "非权威", "非官方来源": True,
            "检索通道": "宿主 WebSearch",
            "段落": [{"id": i, "内容": s} for i, s in enumerate(ab_sents, 1)]}],
            "policyFiles": []}}}
        ext_b = {"content": {"data": {"检索文章": [{
            "文章标题": "外部重复文B", "源网址": "https://example.com/ext-b",
            "数据源": "外部站", "数据权威性": "非权威", "非官方来源": True,
            "检索通道": "宿主 WebSearch",
            "段落": [{"id": i, "内容": s} for i, s in enumerate(
                ab_sents + ["这是外部重复文B多出的一句内容。"], 1)]}],
            "policyFiles": []}}}
        ext_c = {"content": {"data": {"检索文章": [{
            "文章标题": "外部独立文C", "源网址": "https://example.com/ext-c",
            "数据源": "外部站", "数据权威性": "非权威", "非官方来源": True,
            "检索通道": "宿主 WebSearch",
            "段落": [{"id": i, "内容": s} for i, s in enumerate([
                "这是外部独立文的第一句内容。",
                "这是外部独立文的第二句内容。",
                "这是外部独立文的第三句内容。",
                "这是外部独立文的第四句内容。",
            ], 1)]}], "policyFiles": []}}}
        official_ab = {"content": {"data": {"检索文章": [{
            "文章标题": "官方近似文", "源网址": "https://example.gov.cn/official-ab",
            "数据源": "官网", "检索通道": "深知可信搜索",
            "段落": [{"id": i, "内容": s} for i, s in enumerate(ab_sents, 1)]}],
            "policyFiles": []}}}
        write("test_ws_ab_a.json", ext_a)
        write("test_ws_ab_b.json", ext_b)
        write("test_ws_ab_c.json", ext_c)
        write("test_ws_ab_official.json", official_ab)
        _ab_inputs = [("test_ws_ab_a.json", "补充检索"),
                      ("test_ws_ab_b.json", "补充检索"),
                      ("test_ws_ab_c.json", "补充检索"),
                      ("test_ws_ab_official.json", "库内")]
        for _name, _order in (
            ("外部在前", _ab_inputs),
            ("官方在前", [_ab_inputs[3]] + _ab_inputs[:3]),
        ):
            _d = merged(_order)
            _arts = _d["content"]["data"]["检索文章"]
            _stats = _d["search_meta"]["calls"]
            _ext_new = sum(c["new_articles"] for c in _stats if c["label"] == "补充检索")
            _ext_final = sum(1 for a in _arts if a.get("非官方来源"))
            check(f"同权威近似重复回滚（{_name}）：外部新增=最终外部材料数",
                  _ext_new == 1 and _ext_final == 1, f"new={_ext_new}, final={_ext_final}")
            check(f"同权威近似重复回滚（{_name}）：最终 2 篇（外部 C + 官方）",
                  len(_arts) == 2, str(_arts))

        # 重要项 1 回归：convert 与 merge 的 tracking 参数集合一致（source=wechat）
        stage2_src = {"content": {"data": {"检索文章": [{
            "文章标题": "同文 source 参数", "源网址": "https://example.gov.cn/src?source=wechat",
            "数据源": "联网", "非官方来源": True, "检索通道": "深知可信搜索·联网",
            "段落": [{"id": 1, "内容": "联网原段。"}]}], "policyFiles": []}}}
        stage3_src = {"content": {"data": {"检索文章": [{
            "文章标题": "同文 source 参数", "源网址": "https://example.gov.cn/src",
            "数据源": "外部站", "数据权威性": "非权威", "非官方来源": True,
            "检索通道": "宿主 WebSearch", "段落": [{"id": 1, "内容": "外部补充段。"}]}], "policyFiles": []}}}
        write("test_ws_stage2_src.json", stage2_src)
        write("test_ws_stage3_src.json", stage3_src)
        d = merged([("test_ws_stage2_src.json", "补充检索"),
                    ("test_ws_stage3_src.json", "公开资料补充")])
        check("source=wechat 同文合并为 1 篇", len(d["content"]["data"]["检索文章"]) == 1,
              f"got {len(d['content']['data']['检索文章'])}")

        # 重要项 2/3 回归：阶段二外部材料触发页脚/自验收切换；材料级“核验”字段过滤内部词
        render_merged = {"content": {"data": {"检索文章": [{
            "编号": 1, "文章标题": "测试外部文章", "源网址": "https://example.com/a",
            "数据源": "外部站", "检索通道": "深知可信搜索·联网", "非官方来源": True,
            "核验": "阶段三 宿主 WebSearch 外部联网 已核验",
            "段落": [{"id": 1, "内容": "测试外部段落。"}]}], "policyFiles": []}}}
        write("test_ws_render_merged.json", render_merged)
        (RESULTS / "test_ws_render_answer.txt").write_text("# 测试\n\n测试结论[1]。\n", encoding="utf-8")
        (RESULTS / "test_ws_render_selfcheck.json").write_text(json.dumps({
            "fact_basis": "通过：测试", "binding": "通过：测试", "consistency": "通过：测试",
            "freshness": "通过：测试", "no_gap": "通过：测试"}, ensure_ascii=False), encoding="utf-8")
        out_html = SKILL / "official-docs" / "output" / "test_ws_render.html"
        out_html.unlink(missing_ok=True)
        proc = subprocess.run([
            sys.executable, str(SCRIPTS / "render_trace_html.py"), "test_ws_render_merged.json",
            "--answer-file", "test_ws_render_answer.txt",
            "--self-check-file", "test_ws_render_selfcheck.json",
            "--question", "测试", "--output", "test_ws_render.html",
        ], capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stdout + proc.stderr)
        html = out_html.read_text(encoding="utf-8")
        check("阶段二外部材料触发正文提示条", "本页部分材料来自公开网络" in html)
        check("阶段二外部材料触发知识专库页脚", "部分材料来自公开网络" in html)
        check("阶段二外部材料触发自验收文案", "公开网络材料已标注非官方来源" in html)
        check("材料级核验字段过滤内部词",
              "宿主 WebSearch" not in html and "阶段三" not in html and "外部联网" not in html)
        check("外部材料只标非官方来源", "非官方来源" in html and "非官方来源 · 待核验" not in html)

        # 阻塞项 1 渲染回归：库内无权威字段 + 外部同 URL 非权威，不能出现非官方徽标/提示条
        # 重新跑一次 official_noauth 的合并结果（上方 d 已被覆盖，故重建）
        d2 = merged([("test_ws_official_noauth.json", "库内"),
                     ("test_ws_external_noauth.json", "公开资料补充")])
        write("test_ws_render_official.json", d2)
        out2 = SKILL / "official-docs" / "output" / "test_ws_render_official.html"
        out2.unlink(missing_ok=True)
        proc = subprocess.run([
            sys.executable, str(SCRIPTS / "render_trace_html.py"), "test_ws_render_official.json",
            "--answer-file", "test_ws_render_answer.txt",
            "--self-check-file", "test_ws_render_selfcheck.json",
            "--question", "测试", "--output", "test_ws_render_official.html",
        ], capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stdout + proc.stderr)
        html2 = out2.read_text(encoding="utf-8")
        check("库内无权威字段渲染后无正文提示条", "本页部分材料来自公开网络" not in html2)
        check("库内无权威字段渲染后无非官方徽标", "非官方来源" not in html2)

        # 五验待确认项：同一分组标签对应多条 --input 时，过程条增量必须汇总
        stats_same_label = rt.compute_process_stats(
            [{"search_key": "补充检索", "channel": "深知可信搜索", "used": True},
             {"search_key": "补充检索", "channel": "深知可信搜索", "used": True}],
            "",
            [{"label": "补充检索", "new_articles": 0, "added_paragraphs": 0},
             {"label": "补充检索", "new_articles": 1, "added_paragraphs": 2}],
        )
        _delta = (stats_same_label.get("conds") or [{}])[0].get("delta", "")
        check("同名分组 calls 增量汇总", "新增 1 篇" in _delta and "补充 2 段" in _delta, _delta)
    finally:
        for p in RESULTS.glob("test_ws_*"):
            p.unlink(missing_ok=True)
        (SKILL / "official-docs" / "output" / "test_ws_render.html").unlink(missing_ok=True)
        (SKILL / "official-docs" / "output" / "test_ws_render_official.html").unlink(missing_ok=True)

    print(f"\n结果：{PASSED} passed, {FAILED} failed")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
