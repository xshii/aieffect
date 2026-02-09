"""插件系统 - 扩展 aieffect 功能

插件可以提供：
- 自定义收集器（针对特定覆盖率格式）
- 自定义报告器（输出到不同目标）
- 执行前/后钩子

注册插件：创建一个包含 `register(registry)` 函数的模块即可。
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

logger = logging.getLogger(__name__)


class PluginRegistry:
    """插件统一注册表"""

    def __init__(self) -> None:
        self._hooks: dict[str, list[Any]] = {
            "pre_run": [],
            "post_run": [],
            "pre_compile": [],
            "post_compile": [],
        }

    def add_hook(self, event: str, callback: Any) -> None:
        if event not in self._hooks:
            raise ValueError(f"未知的钩子事件: {event}")
        self._hooks[event].append(callback)

    def fire(self, event: str, **kwargs: Any) -> None:
        for callback in self._hooks.get(event, []):
            try:
                callback(**kwargs)
            except Exception:
                logger.exception("插件钩子在事件 '%s' 上出错", event)


def load_plugins(plugin_names: list[str], registry: PluginRegistry) -> None:
    """按模块名加载插件并注册"""
    for name in plugin_names:
        try:
            mod = importlib.import_module(name)
            if hasattr(mod, "register"):
                mod.register(registry)
                logger.info("插件已加载: %s", name)
            else:
                logger.warning("插件 '%s' 没有 register() 函数，跳过。", name)
        except ImportError:
            logger.error("加载插件失败: %s", name)
