"""代码仓注册表 - CRUD 管理

职责：
- 代码仓的注册、查询、列表、删除
- 支持 3 种来源：git / tar / api
"""

from __future__ import annotations

import logging
import re
from typing import Any

from framework.core.exceptions import ValidationError
from framework.core.models import RepoSpec
from framework.core.registry import YamlRegistry

logger = logging.getLogger(__name__)

_SAFE_REF_RE = re.compile(r"^[a-zA-Z0-9_./@\-]+$")


class RepoRegistry(YamlRegistry):
    """代码仓注册表"""

    section_key = "repos"

    def __init__(self, registry_file: str = "") -> None:
        if not registry_file:
            from framework.core.config import get_config
            registry_file = getattr(get_config(), "repos_file", "data/repos.yml")
        super().__init__(registry_file)

    def register(self, spec: RepoSpec) -> dict[str, Any]:
        """注册一个代码仓"""
        if not spec.name:
            raise ValidationError("代码仓 name 为必填")
        if spec.source_type not in ("git", "tar", "api"):
            raise ValidationError(f"不支持的来源类型: {spec.source_type}")
        if spec.source_type == "git" and not spec.url:
            raise ValidationError("git 类型必须指定 url")
        if spec.ref and not _SAFE_REF_RE.match(spec.ref):
            raise ValidationError(f"ref 包含非法字符: {spec.ref}")

        entry: dict[str, Any] = {
            "source_type": spec.source_type,
            "url": spec.url,
            "ref": spec.ref,
            "path": spec.path,
            "tar_path": spec.tar_path,
            "tar_url": spec.tar_url,
            "api_url": spec.api_url,
            "api_token": spec.api_token,
            "setup_cmd": spec.setup_cmd,
            "build_cmd": spec.build_cmd,
            "deps": spec.deps,
        }
        self._put(spec.name, entry)
        logger.info("代码仓已注册: %s (type=%s)", spec.name, spec.source_type)
        return entry

    def get(self, name: str) -> RepoSpec | None:
        """获取已注册代码仓定义"""
        entry = self._get_raw(name)
        if entry is None:
            return None
        return RepoSpec(
            name=name,
            source_type=entry.get("source_type", "git"),
            url=entry.get("url", ""),
            ref=entry.get("ref", "main"),
            path=entry.get("path", ""),
            tar_path=entry.get("tar_path", ""),
            tar_url=entry.get("tar_url", ""),
            api_url=entry.get("api_url", ""),
            api_token=entry.get("api_token", ""),
            setup_cmd=entry.get("setup_cmd", ""),
            build_cmd=entry.get("build_cmd", ""),
            deps=entry.get("deps", []),
        )

    def list_all(self) -> list[dict[str, Any]]:
        """列出所有已注册代码仓"""
        return self._list_raw()

    def remove(self, name: str) -> bool:
        """移除代码仓"""
        if not self._remove(name):
            return False
        logger.info("代码仓已移除: %s", name)
        return True
