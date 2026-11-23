#!/usr/bin/env python3
"""1.8.1 本产品入口包装：来源展示口径（## 清理/待补/公开网站/站点名不当机构）+ 未引用标记 + CLI。"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_report_input as bri  # noqa: E402
import build_trace_input as bt  # noqa: E402

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


def enrich(article):
    materials = [bri.map_merged_article(article)]
    bt.enrich_materials(materials, [article])
    return materials[0]


def main():
    # 1. 多机构串 ## 清理 + 政策类型
    m = enrich({"文章标题": "广东省创业担保贷款实施办法", "文章类型": "policy",
                "发布或实施机构": "广东省人力资源和社会保障厅##、广东省财政厅##",
                "段落": [{"内容": "第一条 为支持创业带动就业……"}]})
    check("多机构 ## 清理", m["发布机构"] == "广东省人力资源和社会保障厅、广东省财政厅", m.get("发布机构"))
    check("政策类型写入素材类型", m.get("素材类型") == "policy")

    # 2. 政策缺机构 → 发文机构待补
    m = enrich({"文章标题": "关于做好某项工作的通知", "文章类型": "policy",
                "段落": [{"内容": "通知正文。"}]})
    check("政策缺机构显示待补", m["发布机构"] == "发文机构待补", m.get("发布机构"))

    # 3. 非政策缺机构 → 公开网站
    m = enrich({"文章标题": "各地优化住房公积金政策", "文章类型": "govSite",
                "段落": [{"内容": "公开报道。"}]})
    check("非政策缺机构显示公开网站", m["发布机构"] == "公开网站", m.get("发布机构"))

    # 4. 带站点标记的脏数据不得当发文机构（门户/网站）
    m = enrich({"文章标题": "多地优化住房公积金政策", "文章类型": "govSite",
                "发布或实施机构": "中国经济网门户网站", "段落": [{"内容": "报道。"}]})
    check("站点名不当机构", m["发布机构"] == "公开网站", m.get("发布机构"))

    # 5. 未引用标记透传
    m = enrich({"文章标题": "未引用的参考材料", "文章类型": "policy",
                "已引用": False, "段落": [{"内容": "参考。"}]})
    check("未引用标记透传", m.get("已引用") is False)

    # 6. CLI：merged → 通用 JSON（含展示口径与文号回填）
    tmp = Path(tempfile.mkdtemp()).resolve()
    run = tmp / "run"
    run.mkdir()
    merged = {"content": {"data": {
        "检索文章": [{
            "编号": 1, "文章标题": "天津市引进人才落户实施办法",
            "发布或实施机构": "天津市人社局##", "文章类型": "policy",
            "段落": [{"内容": "符合条件的学历型人才可随时申请。"}],
            "源网址": "https://hrss.tj.gov.cn/a", "搜索条件": "落户政策",
        }],
        "policyFiles": [{"title": "天津市引进人才落户实施办法", "writtenText": "津人社规〔2026〕1号"}],
    }}}
    (run / "merged.json").write_text(json.dumps(merged, ensure_ascii=False))
    (run / "answer.txt").write_text("学历型人才可随时申请[1]。", encoding="utf-8")
    result = subprocess.run([
        sys.executable, str(ROOT / "scripts" / "build_trace_input.py"), "merged.json",
        "--run", str(run), "--output", "input.json", "--policy-files",
        "--answer-file", "answer.txt", "--question", "天津人才落户条件？",
    ], capture_output=True, text=True)
    check("CLI 入口成功", result.returncode == 0, result.stderr)
    payload = json.loads((run / "input.json").read_text())
    m = payload["materials"][0]
    check("CLI 展示机构去 ##", m.get("发布机构") == "天津市人社局", str(m.get("发布机构")))
    check("CLI 文号回填", m.get("发文字号") == "津人社规〔2026〕1号", str(m.get("发文字号")))
    check("CLI 答案与问题", payload.get("question") == "天津人才落户条件？"
          and "学历型人才" in payload.get("answer", ""))

    print(f"\n结果：{passed} 通过，{failed} 失败")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
