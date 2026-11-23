#!/usr/bin/env python3
"""1.8.1 Key 轻量真实校验：有效 / 401 / 网络降级 / 未配置跳过 / --no-verify-key。"""

import contextlib
import io
import json
import sys
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import initialize as init  # noqa: E402

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


def configured_status():
    status = {
        "api_key_configured": True,
        "api_key_check": "format + 轻量真实检索校验",
        "api_key_env": init.API_KEY_ENV,
        "api_key_source": "keyfile",
        "api_key_hint": None,
        "search_ready": True,
        "search_note": None,
        "key_validated": False,
        "key_validation_error": None,
        "key_validation_ms": None,
    }
    return status


def run_with(verify_result, status=None):
    old_resolve, old_verify = init._resolve_key_value, init._verify_key
    init._resolve_key_value = lambda: "sk-" + "x" * 30
    init._verify_key = lambda key: verify_result
    try:
        return init.apply_key_validation(status or configured_status(), [])
    finally:
        init._resolve_key_value, init._verify_key = old_resolve, old_verify


def main():
    # 1. 格式检查：占位符 / 过短 / 正常
    check("短 sk- 判非法", init._looks_like_key("sk-abc") is False)
    check("占位符判非法", init._looks_like_key("your_api_key_here") is False)
    check("长 sk- 判合法", init._looks_like_key("sk-" + "x" * 40) is True)

    # 2. 有效 Key → ready + key_validated
    status, blocking = run_with((True, None, None))
    check("有效 Key key_validated=true", status["key_validated"] is True)
    check("有效 Key 不阻断", blocking == [] and status["search_ready"] is True)
    check("记录校验耗时", isinstance(status.get("key_validation_ms"), int))

    # 3. 401 → ready=false + api_key_invalid
    status, blocking = run_with((False, "Key 校验失败（鉴权 401）", 401))
    check("401 判 Key 无效", status["search_ready"] is False)
    check("401 追加 api_key_invalid", "api_key_invalid" in blocking)
    check("401 提示重新获取", "重新获取" in str(status.get("search_note")))

    # 4. 网络失败/5xx → 降级放行
    status, blocking = run_with((False, "Key 校验请求未完成：timed out", None))
    check("网络失败不阻断", status["search_ready"] is True and blocking == [])
    check("网络失败 key_validated=false", status["key_validated"] is False)
    check("网络失败提示降级", "降级放行" in str(status.get("search_note")))

    # 4.5 安全风控接口（/v1/guard）探针契约
    class _Resp:
        def __init__(self, body):
            self._body = body.encode("utf-8")

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    with mock.patch.object(init, "_open_request",
                           return_value=_Resp('{"status":"SAFE","request_id":"r1"}')):
        result = init._verify_key("sk-" + "x" * 30)
    check("guard 接口 200 SAFE 判有效", result == (True, None, None))

    def _raise(exc):
        def _inner(*args, **kwargs):
            raise exc
        return _inner

    with mock.patch.object(init, "_open_request",
                           side_effect=_raise(urllib.error.HTTPError(
                               init.KEY_PROBE_URL, 401, "Unauthorized", {}, io.BytesIO(b"")))):
        result = init._verify_key("sk-" + "x" * 30)
    check("guard 接口 401 判无效", result[0] is False and result[2] == 401)

    with mock.patch.object(init, "_open_request",
                           side_effect=_raise(urllib.error.URLError("timed out"))):
        result = init._verify_key("sk-" + "x" * 30)
    check("guard 接口网络失败可降级", result[0] is False and result[2] is None)

    # 重定向不跟随：3xx 不得把 Bearer 转发到其他 host，按失败降级
    check("重定向处理器返回 None", init._NoRedirectHandler().redirect_request(
        None, None, 302, "Found", {}, "https://evil.example/") is None)
    with mock.patch.object(init, "_open_request",
                           side_effect=_raise(urllib.error.HTTPError(
                               init.KEY_PROBE_URL, 302, "Found", {}, io.BytesIO(b"")))):
        result = init._verify_key("sk-" + "x" * 30)
    check("3xx 按失败降级", result[0] is False and result[2] == 302)

    # 探针请求必须走文档契约：/v1/guard + Bearer 头
    check("探针地址为 /v1/guard", init.KEY_PROBE_URL == "https://open.dknowc.cn/v1/guard")
    with mock.patch.object(init, "_open_request",
                           return_value=_Resp('{"status":"SAFE"}')):
        with mock.patch.object(init.urllib.request, "Request") as req_cls:
            init._verify_key("sk-" + "x" * 30)
    header_calls = [c.args for c in req_cls.return_value.add_header.call_args_list]
    check("探针使用 Bearer 鉴权", ("Authorization", "Bearer " + "sk-" + "x" * 30) in header_calls)

    # 5. 未配置 Key → 不发起真实校验
    old = init._verify_key
    init._verify_key = lambda key: (_ for _ in ()).throw(AssertionError("不应发起校验"))
    try:
        status = {"api_key_configured": False, "search_ready": False}
        out, blocking = init.apply_key_validation(status, ["api_key_missing"])
        check("未配置不发校验", blocking == ["api_key_missing"] and out.get("key_validated") is not True)
    finally:
        init._verify_key = old

    # 6. --no-verify-key 跳过
    old_argv = sys.argv
    sys.argv = ["initialize.py", "--no-verify-key"]
    try:
        status, blocking = run_with((False, "不应调用", 401))
        check("--no-verify-key 跳过校验", status.get("key_validated") is not True and blocking == [])
    finally:
        sys.argv = old_argv

    # 7. main 输出包含 key_validated 与 ready 语义
    old_check_api, old_check_update = init.check_api_key_config, init.check_update
    old_resolve, old_verify = init._resolve_key_value, init._verify_key
    init.check_api_key_config = configured_status
    init.check_update = lambda: {"checked": False, "update_available": False}
    init._resolve_key_value = lambda: "sk-" + "x" * 30
    init._verify_key = lambda key: (True, None, None)
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            init.main()
        payload = json.loads(buf.getvalue())
        check("main 输出 key_validated", payload.get("key_validated") is True)
        check("main ready=true", payload.get("ready") is True and payload.get("blocking_issues") == [])
    finally:
        init.check_api_key_config, init.check_update = old_check_api, old_check_update
        init._resolve_key_value, init._verify_key = old_resolve, old_verify

    print(f"\n结果：{passed} 通过，{failed} 失败")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
