"""用例表单管理 - 用例的增删改查与环境绑定

用例存储在 YAML 文件中，每个用例定义：
  - 基本信息（名称、描述、命令模板、标签、超时）
  - 绑定环境列表（指定可在哪些环境下执行）
  - 参数模式（支持手动填写的运行时参数定义）
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

    def _environments(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = self._data.setdefault("environments", {})
        return result

    # ---- 环境管理 ----

    def add_environment(
        self, name: str, description: str = "",
        variables: dict[str, str] | None = None,
    ) -> dict:
        """添加或更新执行环境定义"""
        env = {"description": description, "variables": variables or {}}
        self._environments()[name] = env
        self._save()
        logger.info("环境已保存: %s", name)
        return env

    def list_environments(self) -> list[dict]:
        return [{"name": k, **v} for k, v in self._environments().items()]

    def remove_environment(self, name: str) -> bool:
        envs = self._environments()
        if name not in envs:
            return False
        del envs[name]
        self._save()
        logger.info("环境已删除: %s", name)
        return True

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

        extra 支持: params_schema(dict), repo(dict)
        """
        case: dict[str, object] = {
            "cmd": cmd,
            "description": description,
            "tags": tags or [],
            "timeout": timeout,
            "environments": environments or [],
            "params_schema": extra.get("params_schema") or {},
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

    def to_test_cases(
        self,
        names: list[str] | None = None,
        tag: str | None = None,
        environment: str | None = None,
    ) -> list:
        """将 CaseManager 中的用例转换为 runner.Case 列表

        支持按名称、标签、环境过滤。返回可直接交给 Scheduler.run_all() 的列表。
        """
        from framework.core.models import Case

        cases_data = self.list_cases(tag=tag, environment=environment)
        if names:
            name_set = set(names)
            cases_data = [c for c in cases_data if c["name"] in name_set]

        result = []
        for c in cases_data:
            result.append(Case(
                name=c["name"],
                args={"cmd": c.get("cmd", "")},
                timeout=c.get("timeout", 3600),
                tags=c.get("tags", []),
                environment=c.get("environments", [""])[0] if c.get("environments") else "",
                repo=c.get("repo", {}),
            ))
        return result

    def validate_params(self, name: str, params: dict[str, str]) -> list[str]:
        """校验运行时参数是否满足用例的参数模式，返回错误列表"""
        case = self._cases().get(name)
        if case is None:
            return [f"用例 '{name}' 不存在"]

        errors: list[str] = []
        schema = case.get("params_schema", {})
        for pname, pdef in schema.items():
            value = params.get(pname)
            if value is None:
                default = pdef.get("default")
                if default is None:
                    errors.append(f"缺少必填参数: {pname}")
                continue
            choices = pdef.get("choices")
            if choices and value not in [str(c) for c in choices]:
                errors.append(f"参数 '{pname}' 值 '{value}' 不在可选范围 {choices} 内")
        return errors
