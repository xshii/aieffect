#!/usr/bin/env python3
"""依赖版本覆盖工具

由 Jenkins 流水线调用，在运行时切换依赖版本。

用法:
    # 应用完整的覆盖文件
    python scripts/apply_deps.py --override deps/override_versions.yml

    # 更新单个依赖
    python scripts/apply_deps.py --dep-name model_lib --dep-version v2.1.0

    # 查看当前版本
    python scripts/apply_deps.py --show
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import yaml

from framework.utils.logger import setup_logging

logger = logging.getLogger(__name__)

DEFAULT_VERSIONS_FILE = "deps/tool_versions.yml"


def load_versions(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        logger.warning("版本文件不存在: %s", path)
        return {}
    with open(p) as f:
        return yaml.safe_load(f) or {}


def save_versions(data: dict, path: str) -> None:
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False)
    logger.info("版本信息已保存到 %s", path)


def apply_override(base_path: str, override_path: str) -> None:
    """将覆盖版本合并到基础版本文件"""
    base = load_versions(base_path)
    override = load_versions(override_path)

    if not override:
        logger.warning("覆盖文件为空: %s", override_path)
        return

    deps = base.setdefault("dependencies", {})
    for name, version in override.items():
        old = deps.get(name, {}).get("version", "未设置")
        deps.setdefault(name, {})["version"] = version
        logger.info("  %s: %s -> %s", name, old, version)

    save_versions(base, base_path)


def apply_single(base_path: str, dep_name: str, dep_version: str) -> None:
    """更新单个依赖的版本"""
    base = load_versions(base_path)
    deps = base.setdefault("dependencies", {})
    old = deps.get(dep_name, {}).get("version", "未设置")
    deps.setdefault(dep_name, {})["version"] = dep_version
    logger.info("  %s: %s -> %s", dep_name, old, dep_version)
    save_versions(base, base_path)


def show_versions(base_path: str) -> None:
    """打印当前依赖版本"""
    data = load_versions(base_path)
    deps = data.get("dependencies", {})
    if not deps:
        print("未定义任何依赖。")
        return
    for name, info in sorted(deps.items()):
        version = info.get("version", "未设置") if isinstance(info, dict) else info
        print(f"  {name}: {version}")


def main() -> None:
    parser = argparse.ArgumentParser(description="应用依赖版本覆盖")
    parser.add_argument("--base", default=DEFAULT_VERSIONS_FILE, help="基础版本文件")
    parser.add_argument("--override", help="版本覆盖 YAML 文件")
    parser.add_argument("--dep-name", help="要更新的依赖名")
    parser.add_argument("--dep-version", help="新版本号")
    parser.add_argument("--show", action="store_true", help="显示当前版本")
    args = parser.parse_args()

    setup_logging(level="INFO")

    if args.show:
        show_versions(args.base)
    elif args.override:
        apply_override(args.base, args.override)
    elif args.dep_name and args.dep_version:
        apply_single(args.base, args.dep_name, args.dep_version)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
