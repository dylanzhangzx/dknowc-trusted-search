#!/usr/bin/env python3
"""1.8.0 运行目录隔离回归：产物不得写回 Skill 安装目录，重复运行不覆盖。"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from run_paths import RunPathError, resolve_output_path, resolve_run_dir  # noqa: E402
import trusted_search  # noqa: E402
import deep_query  # noqa: E402

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
    tmp = Path(tempfile.mkdtemp(prefix="trusted-run-test-"))
    run = resolve_run_dir(str(tmp / "run"))
    check("run 目录创建在会话工作区", run == (tmp / "run").resolve(), str(run))

    out1 = resolve_output_path("report.html", run, {".html"}, ".html", "报告.html")
    out1.write_text("first", encoding="utf-8")
    out2 = resolve_output_path("report.html", run, {".html"}, ".html", "报告.html")
    check("首次产物落在 run 目录", out1.parent == run)
    check("重复运行自动 _v2，不覆盖", out2.name == "report_v2.html", out2.name)

    t_out = trusted_search.resolve_output_json("search.json", run)
    d_out = deep_query.resolve_output_json("deep.json", run)
    check("检索脚本产物落在 run 目录", t_out.parent == run and d_out.parent == run)

    try:
        trusted_search.resolve_output_json("search.json", ROOT / "scripts")
        check("检索脚本拒绝 Skill 目录", False)
    except RunPathError:
        check("检索脚本拒绝 Skill 目录", True)

    try:
        resolve_run_dir(str(ROOT / "scripts"))
        check("拒绝 Skill 安装目录作为 run", False)
    except RunPathError:
        check("拒绝 Skill 安装目录作为 run", True)

    try:
        resolve_output_path(str(ROOT / "scripts" / "x.html"), run, {".html"}, ".html", "x.html")
        check("拒绝产物写入 Skill 安装目录", False)
    except RunPathError:
        check("拒绝产物写入 Skill 安装目录", True)

    print(f"\n结果：{passed} 通过，{failed} 失败")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
