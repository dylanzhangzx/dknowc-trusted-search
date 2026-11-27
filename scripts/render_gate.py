#!/usr/bin/env python3
"""渲染闸门包装（1.8.3）：内核 render_trace_html.py 保持上游单源原样，
跨平台成功标记 [GATE-PASS] 由本包装在核验通过后输出——不以修改内核表达产品闸门。

用法与渲染器一致（透传全部参数）：
    python3 scripts/render_gate.py "$RUN/input.json" --run "$RUN" --output "xxx.html"

判据：退出码 0 且输出含 [GATE-PASS]；内核失败（退出码 1/2）时原样透传退出码、不输出标记。
"""

import subprocess
import sys
from pathlib import Path

KERNEL = Path(__file__).resolve().parent / "render_trace_html.py"


def main() -> int:
    proc = subprocess.run([sys.executable, str(KERNEL), *sys.argv[1:]])
    if proc.returncode == 0:
        # 跨平台闸门标记：判据 = 退出码 0 且输出含 [GATE-PASS]（零输出≠通过）
        print("[GATE-PASS] render_gate: 核验报告已生成")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
