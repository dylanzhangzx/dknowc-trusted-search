#!/usr/bin/env python3
"""1.8.3 跨平台闸门：SKILL 命令约定、四个闸门脚本 [GATE-PASS] 标记、check_release 实跑。"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

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
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

    print("== SKILL.md 命令约定（跨平台） ==")
    check("存在跨平台约定节", "## 命令约定（跨平台）" in skill)
    check("Windows 占位符说明", "微软商店" in skill and "占位符" in skill)
    check("替代命令 python/py", "`python`（或 `py`）" in skill)
    check("闸门判据含 [GATE-PASS]", "[GATE-PASS]" in skill)
    check("判据=退出码0且含标记", "退出码 0 且输出含" in skill)
    check("覆盖 reference 声明", "覆盖全部 reference 文档" in skill)
    check("退出码措辞已同步", "`0` 成功（且输出含 `[GATE-PASS]`" in skill)

    print("== 四个闸门脚本标记 ==")
    cases = [
        ("initialize.py", "[GATE-PASS] initialize"),
        ("check_release.py", "[GATE-PASS] check_release"),
        ("render_gate.py", "[GATE-PASS] render_gate"),
        ("build_trace_input.py", "[GATE-PASS] build_trace_input"),
    ]
    for fname, marker in cases:
        src = (SCRIPTS / fname).read_text(encoding="utf-8")
        check(f"{fname} 含成功标记", marker in src)

    init_src = (SCRIPTS / "initialize.py").read_text(encoding="utf-8")
    check("initialize 标记绑定 ready（未就绪不打标）",
          "if not blocking_issues:" in init_src
          and init_src.find("if not blocking_issues:") < init_src.find("[GATE-PASS] initialize"))

    # 1.8.3 归位：内核保持上游 1.0.2 原样（不含产品标记），标记由 render_gate 包装输出
    kernel_src = (SCRIPTS / "render_trace_html.py").read_text(encoding="utf-8")
    check("内核 render 不含产品闸门标记", "[GATE-PASS]" not in kernel_src)
    gate_src = (SCRIPTS / "render_gate.py").read_text(encoding="utf-8")
    check("render_gate 调用内核", "render_trace_html.py" in gate_src and "subprocess.run" in gate_src)
    check("render_gate 成功后才打标", gate_src.find("proc.returncode == 0") < gate_src.find("[GATE-PASS] render_gate"))

    print("== check_release 实跑 ==")
    # 其他测试导入脚本会生成 __pycache__（发布包禁止项），实跑前先清掉本地产物；
    # 同时清 .DS_Store，保证检查器只针对源码内容。
    import shutil
    for cache in ROOT.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    for ds in ROOT.rglob(".DS_Store"):
        try:
            ds.unlink()
        except OSError:
            pass
    proc = subprocess.run([sys.executable, str(SCRIPTS / "check_release.py")],
                          capture_output=True, text=True, timeout=60)
    out = (proc.stdout or "") + (proc.stderr or "")
    check("check_release 退出 0", proc.returncode == 0, out[-300:])
    check("check_release 输出含 [GATE-PASS]", "[GATE-PASS]" in out, out[-300:])

    print(f"\n结果：{passed} 通过，{failed} 失败")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
