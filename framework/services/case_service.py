"""用例管理服务 — CLI 和 Web 共享的用例 CRUD 逻辑"""

from __future__ import annotations

from typing import Any

from framework.core.case_manager import CaseManager
from framework.core.exceptions import CaseNotFoundError, ValidationError


class CaseService:
    """用例管理服务"""

    def __init__(self, case_manager: CaseManager) -> None:
        self.cm = case_manager

    def create(self, *, name: str = "", cmd: str = "", **kwargs: Any) -> dict[str, object]:
        """创建用例，返回完整用例 dict"""
        if not name or not cmd:
            raise ValidationError("name 和 cmd 为必填", details=["name", "cmd"])
        case = self.cm.add_case(name, cmd, **kwargs)
        return {"name": name, **case}

    def get(self, name: str) -> dict:
        case = self.cm.get_case(name)
        if case is None:
            raise CaseNotFoundError(f"用例不存在: {name}")
        return case

    def list_all(
        self, tag: str | None = None, environment: str | None = None,
    ) -> list[dict]:
        return self.cm.list_cases(tag=tag, environment=environment)

    def update(self, name: str, **fields: object) -> dict:
        updated = self.cm.update_case(name, **fields)
        if updated is None:
            raise CaseNotFoundError(f"用例不存在: {name}")
        return updated

    def delete(self, name: str) -> bool:
        if not self.cm.remove_case(name):
            raise CaseNotFoundError(f"用例不存在: {name}")
        return True
