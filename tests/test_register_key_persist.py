#!/usr/bin/env python3
"""register_key.mjs 密钥落盘安全回归（2026-11-09 审核阻塞项 2）。

覆盖：
- 已存在的 0644 Key 文件经 persist 覆写后必须变为 0600；
- 写入使用临时文件 + rename，不残留临时文件；
- 输出 JSON 不再包含明文 apiKey（静态检查源码输出路径）。

用法：python3 tests/test_register_key_persist.py（需要 node）
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPT = SKILL / "scripts" / "register_key.mjs"
NODE = shutil.which("node")
# 运行时拼接，避免源码里出现可被密钥扫描器命中的连续 sk- 字面量
TEST_KEY = "sk-" + "testonly" * 3
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


def main() -> int:
    if not NODE:
        print("跳过：未找到 node")
        return 0

    with tempfile.TemporaryDirectory(prefix="dknowc_key_test_") as td:
        cfg = Path(td) / "dknowc"
        cfg.mkdir()
        keyfile = cfg / "api_key"
        keyfile.write_text("old-key\n", encoding="utf-8")
        os.chmod(keyfile, 0o644)

        env = dict(os.environ)
        env["DKNOWC_CONFIG_DIR"] = str(cfg)
        env["DKNOWC_API_KEY"] = TEST_KEY
        proc = subprocess.run([NODE, str(SCRIPT), "persist"], env=env,
                              capture_output=True, text=True)
        check("persist 退出码 0", proc.returncode == 0, proc.stdout + proc.stderr)
        payload = {}
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            pass
        check("persist 输出 envWriteSucceeded=true", payload.get("envWriteSucceeded") is True, proc.stdout)
        check("已存在的 0644 Key 文件被收紧为 0600",
              (keyfile.stat().st_mode & 0o777) == 0o600,
              oct(keyfile.stat().st_mode & 0o777))
        check("Key 内容写入正确",
              keyfile.read_text(encoding="utf-8").strip() == TEST_KEY)
        check("不残留临时文件", not list(cfg.glob("*.tmp-*")), str(list(cfg.glob("*.tmp-*"))))

    source = SCRIPT.read_text(encoding="utf-8")
    check("注册输出固定 apiKey:null（不再回退明文）", "apiKey: null" in source)
    check("旧明文回退路径已移除", "apiKey: cfgWrite.written ? null : apiKeyToSave" not in source)
    check("落盘使用临时文件+rename", "renameSync(tmpPath, filePath)" in source)
    check("落盘显式 chmod 0600", "chmodSync(tmpPath, 0o600)" in source)
    check("落盘失败+新Key失败话术不矛盾",
          "userMessage += cfgWrite.written" in source and "当前密钥也未安全落盘" in source)

    print(f"\n结果：{PASSED} passed, {FAILED} failed")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
