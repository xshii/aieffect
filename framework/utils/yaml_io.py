"""YAML 文件统一读写工具

集中管理 YAML 文件的序列化/反序列化，避免各模块重复实现。
统一 encoding="utf-8"、空值保护、目录自动创建、原子写入。
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# YAML 文件最大大小限制 (10MB)，防止恶意大文件导致内存耗尽
MAX_YAML_SIZE = 10 * 1024 * 1024


def atomic_write(path: Path, content: str) -> None:
    """原子写入文件：先写临时文件再 rename，防止中途崩溃导致损坏

    参数:
        path: 目标文件路径
        content: 要写入的内容

    异常:
        OSError: 文件写入或移动失败
        PermissionError: 无写入权限

    实现:
        1. 在同目录创建临时文件
        2. 写入内容到临时文件
        3. 原子性地替换目标文件
        4. 如果失败，清理临时文件
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, str(path))
    except Exception:
        # 只捕获普通异常，不拦截 KeyboardInterrupt/SystemExit
        try:
            os.unlink(tmp)
        except OSError:
            # 临时文件清理失败不影响原异常抛出
            pass
        raise


def load_yaml(path: str | Path) -> dict[str, Any]:
    """安全读取 YAML 文件

    参数:
        path: YAML 文件路径

    返回:
        dict: 解析后的字典。如果文件不存在、为空、或内容不是字典类型，返回空字典

    异常:
        PermissionError: 无读取权限
        yaml.YAMLError: YAML 格式错误
        OSError: 其他 IO 错误
        ValueError: 文件过大（超过 MAX_YAML_SIZE）

    示例:
        >>> config = load_yaml("config.yaml")
        >>> version = config.get("version", "1.0")
    """
    p = Path(path)
    if not p.exists():
        return {}

    # 检查文件大小，防止恶意大文件导致内存耗尽
    file_size = p.stat().st_size
    if file_size > MAX_YAML_SIZE:
        raise ValueError(
            f"YAML 文件过大: {p} ({file_size} 字节), "
            f"超过限制 {MAX_YAML_SIZE} 字节"
        )

    try:
        with open(p, encoding="utf-8") as f:
            result = yaml.safe_load(f)

            # 确保返回字典类型
            if result is None:
                return {}
            if not isinstance(result, dict):
                logger.warning(
                    f"{path} 内容不是字典类型 (实际类型: {type(result).__name__})，"
                    "返回空字典"
                )
                return {}

            return result

    except yaml.YAMLError as e:
        logger.error(f"解析 YAML 文件失败: {path}, 错误: {e}")
        raise
    except (PermissionError, OSError) as e:
        logger.error(f"读取文件失败: {path}, 错误: {e}")
        raise


def save_yaml(path: str | Path, data: Any) -> None:
    """原子写入 YAML 文件

    参数:
        path: YAML 文件路径
        data: 要保存的数据（可以是 dict、list 等任何可序列化的类型）

    异常:
        OSError: 文件写入失败
        PermissionError: 无写入权限
        yaml.YAMLError: YAML 序列化失败

    实现:
        - 使用原子写入，防止中途崩溃导致文件损坏
        - 自动创建父目录
        - 统一 UTF-8 编码
        - 保持键顺序，允许 Unicode 字符

    示例:
        >>> save_yaml("config.yaml", {"version": "2.0", "debug": True})
        >>> save_yaml("items.yaml", ["item1", "item2", "item3"])
    """
    p = Path(path)
    try:
        content = yaml.dump(
            data, default_flow_style=False,
            allow_unicode=True, sort_keys=False,
        )
        atomic_write(p, content)
    except yaml.YAMLError as e:
        logger.error(f"序列化 YAML 数据失败: {path}, 错误: {e}")
        raise
    except (PermissionError, OSError) as e:
        logger.error(f"写入文件失败: {path}, 错误: {e}")
        raise
