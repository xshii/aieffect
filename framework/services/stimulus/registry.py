"""激励注册表 - 激励源 CRUD 管理

职责：
- 激励源的注册、查询、列表、删除
- 支持 4 种激励类型：repo / generated / stored / external
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from framework.core.exceptions import ValidationError
from framework.core.models import RepoSpec, StimulusSpec
from framework.core.registry import YamlRegistry

logger = logging.getLogger(__name__)


class StimulusRegistry(YamlRegistry):
    """激励源注册表"""

    section_key = "stimuli"

    def __init__(self, registry_file: str = "") -> None:
        if not registry_file:
            from framework.core.config import get_config
            registry_file = getattr(get_config(), "stimuli_file", "data/stimuli.yml")
        super().__init__(registry_file)

    def register(self, spec: StimulusSpec) -> dict[str, Any]:
        """注册激励源"""
        if not spec.name:
            raise ValidationError("激励 name 为必填")
        if spec.source_type not in ("repo", "generated", "stored", "external"):
            raise ValidationError(f"不支持的激励类型: {spec.source_type}")

        entry: dict[str, Any] = {
            "source_type": spec.source_type,
            "description": spec.description,
            "generator_cmd": spec.generator_cmd,
            "storage_key": spec.storage_key,
            "external_url": spec.external_url,
            "params": spec.params,
            "template": spec.template,
        }
        if spec.repo:
            entry["repo"] = {
                "name": spec.repo.name, "url": spec.repo.url,
                "ref": spec.repo.ref, "path": spec.repo.path,
            }
        self._put(spec.name, entry)
        logger.info("激励已注册: %s (type=%s)", spec.name, spec.source_type)
        return entry

    def get(self, name: str) -> StimulusSpec | None:
        """获取已注册激励源定义"""
        entry = self._get_raw(name)
        if entry is None:
            return None
        repo = None
        if entry.get("repo"):
            r = entry["repo"]
            repo = RepoSpec(
                name=r.get("name", name), url=r.get("url", ""),
                ref=r.get("ref", "main"), path=r.get("path", ""),
            )
        return StimulusSpec(
            name=name,
            source_type=entry.get("source_type", "repo"),
            repo=repo,
            generator_cmd=entry.get("generator_cmd", ""),
            storage_key=entry.get("storage_key", ""),
            external_url=entry.get("external_url", ""),
            description=entry.get("description", ""),
            params=entry.get("params", {}),
            template=entry.get("template", ""),
        )

    def list_all(self) -> list[dict[str, Any]]:
        """列出所有已注册激励源"""
        return self._list_raw()

    def remove(self, name: str) -> bool:
        """移除激励源"""
        if not self._remove(name):
            return False
        logger.info("激励已移除: %s", name)
        return True
