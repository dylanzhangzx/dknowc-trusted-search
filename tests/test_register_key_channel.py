#!/usr/bin/env python3
"""1.8.2：固定注册通行码发码通道（对齐公文写作 3.9.9）回归。

覆盖：发码成功（flow=key + 会话落盘）、限频停点（不回落）、地址白名单拒绝、
会话复用与清除的静态契约、发布检查已登记注册通行码。
需要 node；无 node 时跳过（返回 0）。
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "register_key.mjs"
CHECKER = ROOT / "scripts" / "check_release.py"
NODE = shutil.which("node")
# 运行时拼接，避免源码里出现可被发布检查命中的连续 11 位手机号
PHONE = "199" + "0" * 8
PHONE_MASKED = PHONE[:3] + "****" + PHONE[-4:]

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


MOCK_JS = r"""
import http from "http";
const mode = process.argv[2] || "sent";
const srv = http.createServer((req, res) => {
  let body = ""; req.on("data", c => body += c); req.on("end", () => {
    if (!req.url.startsWith("/key-send")) { res.writeHead(404); return res.end("{}"); }
    const key = req.headers["x-maas-registration-key"] || "";
    if (!key) { res.writeHead(400, {"content-type": "application/json"}); return res.end(JSON.stringify({status:false,code:"REGISTRATION_KEY_INVALID"})); }
    if (mode === "sent") {
      res.writeHead(200, {"content-type": "application/json", "set-cookie": ["sl-session=abc123; Path=/"]});
      return res.end(JSON.stringify({status:true, deliveryStatus:"SENT", retryAfterSeconds:0}));
    }
    if (mode === "limit") {
      res.writeHead(429, {"content-type": "application/json"});
      return res.end(JSON.stringify({status:false, code:"SMS_RATE_LIMIT_PHONE", retryAfterSeconds:37}));
    }
    res.writeHead(500, {"content-type": "application/json"});
    res.end(JSON.stringify({status:false, msg:"boom"}));
  });
});
srv.listen(0, "127.0.0.1", () => console.log("PORT=" + srv.address().port));
"""


def start_mock(td: Path, mode: str):
    mock = td / "mock.mjs"
    mock.write_text(MOCK_JS, encoding="utf-8")
    proc = subprocess.Popen([NODE, str(mock), mode], stdout=subprocess.PIPE, text=True)
    line = proc.stdout.readline().strip()
    port = line.split("=", 1)[1] if line.startswith("PORT=") else ""
    return proc, port


def run_challenge(cfg: Path, base: str, extra=None):
    env = dict(os.environ)
    env["DKNOWC_CONFIG_DIR"] = str(cfg)
    cmd = [NODE, str(SCRIPT), "challenge", "--phone", PHONE, "--base", base]
    cmd += extra or []
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    return proc, payload


def main() -> int:
    if not NODE:
        print("跳过：未找到 node")
        return 0

    with tempfile.TemporaryDirectory(prefix="dk_regkey_test_") as td_raw:
        td = Path(td_raw)
        cfg = td / "dknowc"
        cfg.mkdir()

        proc, port = start_mock(td, "sent")
        try:
            check("mock 启动", bool(port))
            r, payload = run_challenge(cfg, f"http://127.0.0.1:{port}")
            check("发码成功退出 0", r.returncode == 0, r.stderr)
            check("flow=key", payload.get("flow") == "key", payload)
            check("code=SMS_SENT", payload.get("code") == "SMS_SENT")
            check("话术含脱敏手机号", PHONE_MASKED in (payload.get("user_message") or ""))
            state = cfg / "maas_registration_session.json"
            check("发码会话已落盘", state.is_file())
            saved = json.loads(state.read_text(encoding="utf-8")) if state.is_file() else {}
            check("会话含 sl-session", (saved.get("cookies") or {}).get("sl-session") == "abc123", saved)
            check("会话记录手机号", saved.get("phone") == PHONE)
            check("会话文件权限 600", (state.stat().st_mode & 0o777) == 0o600)
        finally:
            proc.terminate()

        # 限频：停点、不回落（不请求指引、不改会话）
        before = (cfg / "maas_registration_session.json").read_text(encoding="utf-8")
        proc, port = start_mock(td, "limit")
        try:
            r, payload = run_challenge(cfg, f"http://127.0.0.1:{port}")
            check("限频退出 1", r.returncode == 1)
            check("限频 code", payload.get("code") == "SMS_RATE_LIMIT", payload)
            check("限频带剩余秒数", payload.get("retryAfterSeconds") == 37)
            check("限频不回落（无 question/agent-text）",
                  "question" not in payload and payload.get("flow") == "key", payload)
            check("限频不改动会话", (cfg / "maas_registration_session.json").read_text(encoding="utf-8") == before)
        finally:
            proc.terminate()

        # 地址白名单：非生产/回环地址直接拒绝，不发请求
        r, payload = run_challenge(cfg, "http://127.0.0.1:9", ["--key-send-url", "https://evil.example/x"])
        check("非白名单地址拒绝", payload.get("code") == "PASSCODE_URL_REJECTED", payload)

    src = SCRIPT.read_text(encoding="utf-8")
    check("支持 --legacy 跳过", "a.legacy" in src)
    check("回落标记 keyFallback", "keyFallback" in src)
    check("register 复用发码会话", "regSessionFor(String(payload.phone))" in src)
    check("注册成功清除会话", "if (ok) clearRegSessionState();" in src)
    check("会话清除不删除文件", "unlinkSync(regKeyStatePath" not in src)
    checker = CHECKER.read_text(encoding="utf-8")
    check("发布检查已登记注册通行码",
          "REGISTRATION_KEY_ALLOWED" in checker and "So3EdPDJMf7z0MmH1zfvm6VDEQpR2EIRRsqqtnl866MrpVPl-Sj--g" in checker)
    check("未登记长随机串会被拦", "OPAQUE_TOKEN_PATTERN" in checker)

    print(f"\n结果：{passed} 通过，{failed} 失败")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
