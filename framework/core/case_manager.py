"""用例表单管理 - 用例的增删改查与环境绑定

用例存储在 YAML 文件中，每个用例定义：
  - 基本信息（名称、描述、命令模板、标签、超时）
  - 绑定环境列表（指定可在哪些环境下执行）
"""

from __future__ import annotations

import logging
from typing import Any

from framework.core.registry import YamlRegistry

logger = logging.getLogger(__name__)


class CaseManager(YamlRegistry):
    """用例表单管理器"""

    section_key = "cases"

    def __init__(self, cases_file: str = "") -> None:
        if not cases_file:
            from framework.core.config import get_config
            cases_file = get_config().cases_file
        super().__init__(cases_file)

    def _cases(self) -> dict[str, dict[str, Any]]:
        return self._section()

    # ---- 用例 CRUD ----

    def add_case(
        self,
        name: str,
        cmd: str,
        *,
        description: str = "",
        tags: list[str] | None = None,
        timeout: int = 3600,
        environments: list[str] | None = None,
        **extra: Any,
    ) -> dict:
        """添加或更新用例定义

        extra 支持: repo(dict)
        """
        case: dict[str, object] = {
            "cmd": cmd,
            "description": description,
            "tags": tags or [],
            "timeout": timeout,
            "environments": environments or [],
        }
        if extra.get("repo"):
            case["repo"] = extra["repo"]
        self._cases()[name] = case
        self._save()
        logger.info("用例已保存: %s", name)
        return case

    def get_case(self, name: str) -> dict | None:
        case = self._cases().get(name)
        if case is None:
            return None
        return {"name": name, **case}

    def list_cases(self, tag: str | None = None, environment: str | None = None) -> list[dict]:
        """列出用例，支持按标签和环境过滤"""
        result = []
        for name, info in self._cases().items():
            if tag and tag not in info.get("tags", []):
                continue
            if environment and environment not in info.get("environments", []):
                continue
            result.append({"name": name, **info})
        return result

    def update_case(self, name: str, **fields: object) -> dict | None:
        """更新用例的指定字段"""
        cases = self._cases()
        if name not in cases:
            return None
        cases[name].update(fields)
        self._save()
        logger.info("用例已更新: %s", name)
        return {"name": name, **cases[name]}

    def remove_case(self, name: str) -> bool:
        cases = self._cases()
        if name not in cases:
            return False
        del cases[name]
        self._save()
        logger.info("用例已删除: %s", name)
        return True
