#!/usr/bin/env python3
"""发布检查：产品身份与版本三件套（防止 SKILL.md/CHANGE_log 被其他产品文件覆盖）。"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_release as cr  # noqa: E402

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


def with_root(root, fn):
    old = cr.SKILL_ROOT
    cr.SKILL_ROOT = Path(root)
    try:
        return fn()
    finally:
        cr.SKILL_ROOT = old


def make_root(skill_text, changelog_text=""):
    tmp = Path(tempfile.mkdtemp()).resolve()
    (tmp / "SKILL.md").write_text(skill_text, encoding="utf-8")
    if changelog_text:
        (tmp / "CHANGE_log.md").write_text(changelog_text, encoding="utf-8")
    return tmp


def main():
    # 1. 正常身份 + 版本条目
    good = make_root(
        '---\nname: 深知可信搜索（法律、政策、标准）\nversion: "1.8.1"\n---\n\n正文',
        "# 更新日志\n\n## [1.8.1] - 2026-11-23\n")
    findings = with_root(good, cr.check_product_identity)
    check("正常身份无告警", findings == [], str(findings))

    # 2. 被其他产品覆盖（name 不符）
    wrong = make_root(
        '---\nname: 溯源核验报告生成器\nversion: "1.0.1"\n---\n\n正文',
        "# 更新日志\n\n## [1.0.1]\n")
    findings = with_root(wrong, cr.check_product_identity)
    check("产品名不符被拦截", any("产品身份不符" in f for f in findings), str(findings))

    # 3. CHANGE_log 缺当前版本条目
    mismatch = make_root(
        '---\nname: 深知可信搜索（法律、政策、标准）\nversion: "1.8.1"\n---\n\n正文',
        "# 更新日志\n\n## [1.8.0]\n")
    findings = with_root(mismatch, cr.check_product_identity)
    check("版本条目缺失被拦截", any("缺少当前版本条目" in f for f in findings), str(findings))

    # 4. version 格式非法
    badver = make_root('---\nname: 深知可信搜索\nversion: "vNext"\n---\n', "")
    findings = with_root(badver, cr.check_product_identity)
    check("版本格式非法被拦截", any("version" in f for f in findings), str(findings))

    print(f"\n结果：{passed} 通过，{failed} 失败")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
