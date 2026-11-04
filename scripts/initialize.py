#!/usr/bin/env python3
"""深知可信搜索 public 版初始化检查。

API Key 读取：优先进程环境变量 DKNOWC_API_KEY，缺失时从本机专用配置文件
~/.config/dknowc/api_key 读取（不读取、不改写任何 shell 配置文件）
（宿主进程早于 key 写入启动、或宿主安全更新后不再加载 shell 导出变量时不误报缺失）。
注册脚本 register_key.mjs 注册成功后自动把 Key 写入专用配置文件（不写入、不改写任何 shell 配置文件），
本检查直读该文件，无需重启宿主。不读取、不写入本地 config.ini 中的 Key。

版本自检（引导式升级）：匿名查询 MaaS 技能目录公开接口，与本技能 SKILL.md 版本比较，
仅远端版本更高时提示（不提示降级）。结果带 24h 本地缓存、3s 超时静默失败，
任何失败都不阻断初始化、不影响退出语义；升级动作由 Agent 在用户明确同意后执行（见 SKILL.md）。
"""

import json
import os
import re
import shutil
import sys
import time
import urllib.request
from pathlib import Path


API_KEY_ENV = "DKNOWC_API_KEY"
MAAS_PLATFORM_URL = "https://platform.dknowc.cn/auth/#/login"
PLACEHOLDER_KEYS = {"", "your_api_key_here", "你的深知可信搜索 API Key", "你的深知搜索 API Key"}

# 版本自检：MaaS 技能中心公开目录接口（与平台技能中心页面同源，免认证、不扣积分）。
# 目录与下载地址均为固定常量（不接受环境变量覆写，防止更新源被替换）；
# download_url 必须落在官方 OSS 白名单前缀内，download_name 必须等于本技能 slug 包名。
# DKNOWC_UPDATE_CHECK=0 可整体停用自检（用户侧 opt-out）。
UPDATE_CATALOG_URL = "https://platform.dknowc.cn/open-api/maas/skills/v1/catalog"
UPDATE_TARGET_SLUG = "dknowc-trusted-search-maas"
# 升级目标（官方 maas 包）的 SKILL.md name——与 slug/downloadName 一样是已知常量。
# 验包按此常量校验（防投毒＝确认下载的是官方包），不用本地 name：各渠道本地 name
# 可能存在既定特化（如 skills-sh 为 ASCII 目录名形态），拿本地身份校验官方包会把
# 特化渠道的升级全部判失败。
UPDATE_TARGET_NAME = "深知可信搜索（法律、政策、标准）"
UPDATE_DOWNLOAD_PREFIX = "https://down.dknowc.cn/upload/maas/skills/"
UPDATE_DOWNLOAD_NAME = "dknowc-trusted-search-maas.zip"
UPDATE_INSTALL_DOC = "https://platform.dknowc.cn/agent-docs/skills/install.md"
UPDATE_CACHE_TTL_SECONDS = 24 * 3600
UPDATE_TIMEOUT_SECONDS = 3

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _looks_like_key(value: str) -> bool:
    value = (value or "").strip()
    return value not in PLACEHOLDER_KEYS and value.startswith("sk-")


def check_api_key_config():
    # 环境变量优先，缺失时从专用配置文件读取（不涉及 shell 配置文件）
    api_key = ""
    source = ""
    try:
        from api_key import resolve_api_key
        api_key, source = resolve_api_key()
    except ImportError:
        api_key = os.environ.get(API_KEY_ENV, "").strip()
        source = "environment" if api_key else ""
    if _looks_like_key(api_key):
        return {
            "api_key_configured": True,
            "api_key_env": API_KEY_ENV,
            "api_key_source": source or "environment",
            "api_key_hint": None,
            "search_ready": True,
            "search_note": None,
        }

    return {
        "api_key_configured": False,
        "api_key_env": API_KEY_ENV,
        "api_key_source": None,
        "api_key_hint": f"本 Skill 需要通过 {API_KEY_ENV} 连接深知可信智能服务以获取可信内容。当前未检测到可用 Key，请先注册或登录深知智能 MaaS 账号并获取 API Key。",
        "search_ready": False,
        "search_note": f"当前缺少 {API_KEY_ENV}，暂时不能查询政策法规、办事流程、标准依据和可信溯源内容。",
    }


def _package_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _dknowc_config_dir() -> Path:
    # 与 api_key.py 同一套跨平台约定：macOS/Linux 用 ~/.config/dknowc，Windows 用 %APPDATA%/dknowc
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home())
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "dknowc"


def _local_skill_version() -> str:
    try:
        text = (_package_root() / "SKILL.md").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    for line in text.splitlines()[:40]:
        m = re.match(r'^version:\s*["\']?([0-9][0-9A-Za-z.\-]*)', line.strip())
        if m:
            return m.group(1)
    return ""


def _channel_of_this_install() -> str:
    try:
        data = json.loads((_package_root() / "attribution.json").read_text(encoding="utf-8", errors="ignore"))
        return str(data.get("channel") or "")
    except Exception:
        return ""


def _parse_version(version: str) -> tuple:
    parts = []
    for piece in str(version or "").split("."):
        m = re.match(r"^(\d+)", piece)
        parts.append(int(m.group(1)) if m else 0)
    return tuple(parts) or (0,)


def _update_cache_path() -> Path:
    return _dknowc_config_dir() / "update_check.json"


def _read_update_cache():
    try:
        return json.loads(_update_cache_path().read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None


def _write_update_cache(latest, download_url, download_name):
    # 原子写（临时文件＋replace）＋0600 权限，避免半截缓存与权限放大；保留已记录的拒绝版本
    try:
        path = _update_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        old = _read_update_cache() or {}
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps({
            "checked_at": time.time(),
            "latest_version": latest,
            "download_url": download_url,
            "download_name": download_name,
            "declined_version": old.get("declined_version"),
        }, ensure_ascii=False), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except Exception:
        pass


def set_declined_version(version) -> bool:
    """记录用户拒绝的版本（原子合并写入，保留既有字段）。被拒版本不再提示，
    目录出现更高版本时恢复提示；用户主动要求升级时不受此记录影响。"""
    try:
        path = _update_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = _read_update_cache() or {}
        data["declined_version"] = str(version)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def _catalog_entry_is_safe(latest, download_url, download_name) -> bool:
    """目录条目硬校验：版本号必须是纯数字点分格式（防提示语注入），
    下载地址必须落在官方 OSS 白名单前缀内、文件名必须等于本技能包名（防替换下载源）。"""
    if not re.fullmatch(r"\d+(\.\d+)*", str(latest or "")):
        return False
    if not str(download_url or "").startswith(UPDATE_DOWNLOAD_PREFIX):
        return False
    if str(download_name or "") != UPDATE_DOWNLOAD_NAME:
        return False
    return True


def _fetch_catalog_entry():
    # 匿名 GET 公开技能目录，按 slug 定位本技能条目；任何网络/解析失败都返回 None（静默降级）。
    try:
        req = urllib.request.Request(UPDATE_CATALOG_URL, headers={"User-Agent": "dknowc-trusted-search-update-check"})
        with urllib.request.urlopen(req, timeout=UPDATE_TIMEOUT_SECONDS) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
        for entry in (payload or {}).get("data") or []:
            if entry.get("slug") == UPDATE_TARGET_SLUG or entry.get("canonicalSlug") == UPDATE_TARGET_SLUG:
                return entry
    except Exception:
        pass
    return None


def check_update() -> dict:
    """版本自检：远端（MaaS 目录登记版本）> 本地（SKILL.md version）才提示更新，绝不提示降级。

    全程 try/except 兜底——检查失败只置 checked=false，不抛错、不影响退出码与 ready 语义。
    """
    result = {
        "checked": False, "source": None, "current_version": None, "latest_version": None,
        "update_available": False, "download_url": None, "download_name": None,
        "install_doc": UPDATE_INSTALL_DOC, "message": None, "reason": None,
    }
    try:
        if os.environ.get("DKNOWC_UPDATE_CHECK", "").strip() == "0":
            result["reason"] = "disabled_by_env"
            return result
        # volcengine 渠道包为平台特化形态（无注册 onboarding 等），不引导跨渠道替换
        if _channel_of_this_install() == "volcengine":
            result["reason"] = "channel_disabled"
            return result

        current = _local_skill_version()
        result["current_version"] = current or None

        cache = _read_update_cache()
        if cache and (time.time() - float(cache.get("checked_at") or 0)) < UPDATE_CACHE_TTL_SECONDS:
            latest = cache.get("latest_version")
            download_url = cache.get("download_url")
            download_name = cache.get("download_name")
            source = "cache"
        else:
            entry = _fetch_catalog_entry() or {}
            latest = entry.get("version")
            download_url = entry.get("downloadUrl")
            download_name = entry.get("downloadName")
            if latest:
                _write_update_cache(latest, download_url, download_name)
            source = "live"

        if not latest:
            result["reason"] = "catalog_unavailable"
            return result
        if not _catalog_entry_is_safe(latest, download_url, download_name):
            # 版本格式非法／下载地址不在官方白名单／包名不符：一律视为目录不可用，不提示升级
            result["reason"] = "catalog_entry_rejected"
            return result
        result.update({
            "checked": True, "source": source, "latest_version": str(latest),
            "download_url": download_url, "download_name": download_name,
        })
        declined = (cache or {}).get("declined_version") if isinstance(cache, dict) else None
        if declined and _parse_version(latest) <= _parse_version(declined):
            # 用户已拒绝过该版本（或更早版本）：不再提示，目录出现更高版本时恢复提示
            result["reason"] = "declined"
            return result
        if current and _parse_version(latest) > _parse_version(current):
            result["update_available"] = True
            result["message"] = (
                f"检测到「深知可信搜索（法律、政策、标准）」有新版本 v{latest}（当前安装 v{current}）。"
                "升级说明：本技能将更新为官方发布的最新版本；"
                "你的 API Key 与本机配置全部保留，无需重新注册。"
                "是否现在升级？确认后我先完成升级再继续处理你的任务；"
                "选择跳过则这个版本不再提醒、直接继续你的任务。"
            )
            # instruction：脚本输出指令（与 user_message 同级约束）——弱模型对远距离义务
            # （读规则与履约之间隔着整个任务）容易丢失，必须在输出内自带即时行为指令；
            # 命令一律给绝对路径（按抄执行不依赖当前目录），并覆盖升级失败分支。
            updater = str(Path(__file__).resolve().parent / "update_skill.py")
            result["instruction"] = (
                "【开始执行用户任务前必须先履行】现在就向用户原样转述上述 message 征询是否升级"
                "（每个会话最多提示一次），得到答复前不得开始处理任务。用户同意→运行 "
                f"python3 \"{updater}\" --yes 并向用户转述输出中的 user_message，"
                "升级完成后继续用户任务；用户拒绝或跳过→运行 "
                f"python3 \"{updater}\" --decline（静默记录，无需转述），"
                "随后直接继续用户任务，本会话不再提及版本话题。"
                "升级脚本退出码非 0 时（2 无更新／3 下载或验包失败／4 已自动回滚）："
                "如实向用户转述其 user_message 后直接继续用户原任务（当前版本功能完好），"
                "不重试、不手工下载替换，本会话不再提及版本话题。"
            )
    except Exception:
        result["reason"] = result["reason"] or "error"
    return result


def main():
    status = check_api_key_config()
    blocking_issues = []
    if not status["api_key_configured"]:
        blocking_issues.append("api_key_missing")

    # node 运行时只影响注册链路（register_key.mjs），检索本身用 python3 即可，不作为阻断项。
    node_available = shutil.which("node") is not None

    print(json.dumps({
        **status,
        "python_executable": sys.executable,
        "node_available": node_available,
        "blocking_issues": blocking_issues,
        "ready": not blocking_issues,
        # guide_message：需要检索但 Key 未配置时给用户的引导话术（S1 三段式：价值 / 开通方式 / 退路+样例钩子）。
        # Agent 在检索方向确认后向用户转述本话术（可结合任务补充上下文），要素不得删改。
        "guide_message": None if status["api_key_configured"] else (
            "这个问题涉及政策口径和具体数字——普通搜索结果来源杂、无法核验，凭印象答政策名和数字，口径错了会影响你的判断和决策。"
            "开通权威检索后，每条政策、数据都带原文出处、可点开核验，还会附一份可点击的溯源报告。\n"
            "开通是免费的：注册即赠送 10 万积分，完成实名认证再送 10 万积分。"
            "只需手机号收一次验证码——约 10 秒，不用自己填注册表，剩下的我来办；手机号仅用于本次验证，不会有营销骚扰。\n"
            "也可以先不开通：我先基于已有知识给你一版初步回答，涉及政策口径、数字的地方逐条标注\"依据待核验\"，"
            "并说明未联网检索、口径可能过期。想先看看开通后检索结果和溯源报告长什么样，我可以发你示例看看。"
        ),
        # env_message：注册所需运行环境缺失时给用户的统一话术——不暴露组件名（node 对用户无意义）；
        # 就绪时不输出任何环境话题。完整场景话术见 reference/onboarding_scripts.md S6。
        "env_message": (
            "检测到本机开通检索还差一个小程序环境（约 1 分钟，只装一次），我现在装好可以吗？"
            if not node_available else None
        ),
        # update：版本自检结果。update_available=true 时 Agent 在本次任务交付后转述 message 征询
        # （每会话最多一次；用户拒绝则运行 update_skill.py --decline 静默记录）；checked=false
        # （网络不可达/停用/渠道除外/reason=declined）时不得向用户提及版本话题，直接继续原任务。
        "update": check_update(),
        "maas_platform_url": MAAS_PLATFORM_URL,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
