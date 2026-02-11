"""YAML 文件统一读写工具

集中管理 YAML 文件的序列化/反序列化，避免各模块重复实现。
统一 encoding="utf-8"、空值保护、目录自动创建、原子写入。
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def atomic_write(path: Path, content: str) -> None:
    """原子写入文件：先写临时文件再 rename，防止中途崩溃导致损坏"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, str(path))
    except BaseException:
        os.unlink(tmp)
        raise


def load_yaml(path: str | Path) -> dict:
    """安全读取 YAML 文件，文件不存在或为空时返回空 dict"""
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: str | Path, data: dict) -> None:
    """原子写入 YAML 文件，自动创建父目录"""
    p = Path(path)
    content = yaml.dump(
        data, default_flow_style=False,
        allow_unicode=True, sort_keys=False,
    )
    atomic_write(p, content)
