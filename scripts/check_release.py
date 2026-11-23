#!/usr/bin/env python3
"""阻止 API Key、真实配置和本地生成物进入 SkillHub 公开包。"""

import re
from pathlib import Path


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


SKILL_ROOT = Path(__file__).resolve().parent.parent
SKIP_PARTS = {".git"}
BANNED_DIRS = {"outputs"}
WORKSPACE_DIR = SKILL_ROOT / "official-docs"
ALLOWED_WORKSPACE_FILES = {".gitkeep"}
SKIP_FILES = {"CHANGE_log.md"}
BANNED_FILES = {"config.ini", "_meta.json", "config.ini.example"}
BANNED_ARTIFACT_NAMES = {".DS_Store"}
BANNED_ARTIFACT_SUFFIXES = {".pyc", ".pyo"}
# 对内人名/内部称呼不随公开包分发（2026-11-09 审核建议：原为空元组，无法拦截）
BANNED_TERMS: tuple = (
    "徐剑军", "宋紫嫣", "周领权", "金帅澎", "侍纪伟", "李汉文", "曹余健", "惠晓东",
    "张子玄", "徐总",
)
ALLOWED_API_KEY_VALUES = {"", "your_api_key_here", "你的深知可信搜索 API Key", "你的深知搜索 API Key"}
API_KEY_PATTERN = re.compile(r"(?im)^\s*api_key[^\S\r\n]*=[^\S\r\n]*([^\s#;]+)[^\S\r\n]*$")
SECRET_TOKEN_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")
# 手机号红线（2026-10-29 审核新增）：对外话术/文档不得出现完整 11 位手机号，
# 也不得出现脱敏形式的具体号码（模板一律用 <脱敏手机号> 占位、运行时由脚本 user_message 填充）
FULL_PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
MASKED_PHONE_PATTERN = re.compile(r"1[3-9]\d\*{4}\d{4}")
# 产品身份（2026-11-23 审核观察 2）：防止 SKILL.md/CHANGE_log 被其他产品同名文件覆盖后仍通过发布检查
EXPECTED_PRODUCT_NAME = "深知可信搜索"


def _frontmatter(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    data = {}
    for line in text[3:end].splitlines():
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if match:
            data[match.group(1)] = match.group(2).strip().strip('"').strip("'")
    return data


def check_product_identity() -> list:
    """产品身份与版本三件套自检：SKILL.md 名称/版本 + CHANGE_log 当前版本条目。"""
    findings = []
    fm = _frontmatter(SKILL_ROOT / "SKILL.md")
    name = fm.get("name", "")
    version = fm.get("version", "")
    if EXPECTED_PRODUCT_NAME not in name and "dknowc-trusted-search" not in name:
        findings.append(
            f"SKILL.md: 产品身份不符（name={name!r}，应为「{EXPECTED_PRODUCT_NAME}」系列）——"
            "疑似被其他产品的同名文件覆盖")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        findings.append(f"SKILL.md: version 缺失或格式非法（{version!r}）")
    changelog = SKILL_ROOT / "CHANGE_log.md"
    if changelog.is_file():
        try:
            text = changelog.read_text(encoding="utf-8")
        except OSError:
            text = ""
        if version and f"## [{version}]" not in text and f"## {version}" not in text:
            findings.append(
                f"CHANGE_log.md: 缺少当前版本条目 ## [{version}]（SKILL.md/CHANGE_log 版本不一致）")
    return findings


def main():
    findings = check_product_identity()
    for path in SKILL_ROOT.rglob("*"):
        if path.name in BANNED_ARTIFACT_NAMES or path.suffix in BANNED_ARTIFACT_SUFFIXES:
            findings.append(f"{path.relative_to(SKILL_ROOT)}: 公开包不得包含本地产物或平台不允许的文件")
            continue
        if any(part in BANNED_DIRS for part in path.relative_to(SKILL_ROOT).parts):
            findings.append(f"{path.relative_to(SKILL_ROOT)}: 公开包不得包含本地生成输出目录")
            continue
        if any(part == "__pycache__" for part in path.parts):
            findings.append(f"{path.relative_to(SKILL_ROOT)}: 公开包不得包含 __pycache__")
            continue
        if path.is_file() and path.name in BANNED_FILES:
            findings.append(f"{path.relative_to(SKILL_ROOT)}: 公开包不得包含真实配置文件")
            continue
        if path.is_file() and _is_within(path, WORKSPACE_DIR) and path.name not in ALLOWED_WORKSPACE_FILES:
            findings.append(f"{path.relative_to(SKILL_ROOT)}: official-docs/ 工作区内只允许 .gitkeep 占位，公开包不得包含工作区产物")
            continue
        if not path.is_file() or path.name in SKIP_FILES or any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.name == "check_release.py":
            # 检查器自身包含 BANNED_TERMS 名单，跳过自检避免误报
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            for term in BANNED_TERMS:
                if term in line:
                    findings.append(f"{path.relative_to(SKILL_ROOT)}:{line_number}: {term}")
        if path.suffix != ".py":
            for match in API_KEY_PATTERN.finditer(text):
                if match.group(1) not in ALLOWED_API_KEY_VALUES:
                    findings.append(f"{path.relative_to(SKILL_ROOT)}: 发现非占位符 api_key")
        if SECRET_TOKEN_PATTERN.search(text):
            findings.append(f"{path.relative_to(SKILL_ROOT)}: 发现疑似 API Key")
        for line_number, line in enumerate(text.splitlines(), 1):
            if FULL_PHONE_PATTERN.search(line):
                findings.append(f"{path.relative_to(SKILL_ROOT)}:{line_number}: 发现完整手机号（不得写入对外包）")
            if MASKED_PHONE_PATTERN.search(line):
                findings.append(f"{path.relative_to(SKILL_ROOT)}:{line_number}: 发现脱敏手机号具体示例（请改用 <脱敏手机号> 占位）")

    if findings:
        print("发布检查失败：发现不应进入 SkillHub 公开包的内容")
        print("\n".join(findings))
        raise SystemExit(1)
    print("发布检查通过：未发现真实配置、API Key 或本地生成物")


if __name__ == "__main__":
    main()
