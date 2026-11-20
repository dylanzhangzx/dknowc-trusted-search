#!/usr/bin/env python3
"""运行目录与产物路径：业务产物只写会话工作区，永不写回 Skill 安装目录。

约定：
- `--run` 指定本次运行的独立目录；目录已存在且非空时自动改用 `<name>-2`、`-3`，不覆盖旧 run；
- 相对输出名一律落在 run 目录；绝对输出也必须是 Skill 安装目录之外；
- 输入允许绝对路径或 run 目录内相对路径；为兼容旧产物，也允许从 Skill 目录读取。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

SKILL_ROOT = Path(__file__).resolve().parent.parent


class RunPathError(ValueError):
    """运行目录/产物路径不合法。"""


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _unique_file(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.stem}_v{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RunPathError(f"同名产物过多，无法生成新文件: {path}")


def resolve_run_dir(value: str) -> Path:
    if not value or not str(value).strip():
        raise RunPathError("必须用 --run 指定会话工作区中的独立运行目录（不得使用 Skill 安装目录）")
    raw = Path(value).expanduser()
    resolved = raw.resolve() if raw.is_absolute() else (Path.cwd() / raw).resolve()
    if resolved == SKILL_ROOT or is_within(resolved, SKILL_ROOT):
        raise RunPathError(f"运行目录不能位于 Skill 安装目录内: {resolved}")
    if resolved.exists() and not resolved.is_dir():
        raise RunPathError(f"运行目录不是目录: {resolved}")
    # 复用已有 run 目录；同名产物由 resolve_output_path 自动 _v2/_v3，不覆盖旧文件。
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def resolve_output_path(value: Optional[str], run_dir: Optional[Path],
                        suffixes: Iterable[str], default_suffix: str,
                        default_name: str) -> Path:
    if value:
        raw = Path(value).expanduser()
        if raw.is_absolute():
            target = raw.resolve()
        elif run_dir is not None:
            target = (run_dir / raw).resolve()
        else:
            target = (Path.cwd() / raw).resolve()
    else:
        if run_dir is None:
            raise RunPathError("未指定 --run，也没有给出绝对 --output")
        target = (run_dir / default_name).resolve()

    allowed = {suffix.lower() for suffix in suffixes}
    if target.suffix.lower() not in allowed:
        target = target.with_suffix(default_suffix)
    if target == SKILL_ROOT or is_within(target, SKILL_ROOT):
        raise RunPathError(f"产物不能写入 Skill 安装目录: {target}")
    target = _unique_file(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def resolve_input_path(value: str, run_dir: Optional[Path], suffixes: Iterable[str]) -> Path:
    raw = Path(value).expanduser()
    candidates = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        if run_dir is not None:
            candidates.append(run_dir / raw)
        candidates.append(Path.cwd() / raw)
        candidates.append(SKILL_ROOT / raw)

    resolved = None
    for candidate in candidates:
        if candidate.is_file():
            resolved = candidate.resolve()
            break
    if resolved is None:
        raise RunPathError(f"输入文件不存在: {value}")

    allowed = {suffix.lower() for suffix in suffixes}
    if resolved.suffix.lower() not in allowed:
        raise RunPathError(f"输入文件后缀必须是 {sorted(allowed)} 之一: {value}")
    return resolved
