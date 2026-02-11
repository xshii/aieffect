"""激励服务 — 激励源注册 / 获取 / 生成

激励（stimulus）是驱动 DUT 的测试输入，来源可以是：
  - repo: 从代码仓中检出
  - generated: 通过命令动态生成
  - stored: 从 Storage 中取回
  - external: 从外部 URL 下载
"""

from __future__ import annotations

import hashlib
import logging
import shlex
import subprocess
from pathlib import Path
from typing import Any

from framework.core.exceptions import CaseNotFoundError, ValidationError
from framework.core.models import RepoSpec, StimulusArtifact, StimulusSpec
from framework.utils.yaml_io import load_yaml, save_yaml

logger = logging.getLogger(__name__)


class StimulusService:
    """激励生命周期管理"""

    def __init__(self, registry_file: str = "", artifact_dir: str = "") -> None:
        if not registry_file:
            from framework.core.config import get_config
            registry_file = getattr(get_config(), "stimuli_file", "data/stimuli.yml")
        if not artifact_dir:
            from framework.core.config import get_config
            artifact_dir = str(Path(get_config().workspace_dir) / "stimuli")
        self.registry_file = Path(registry_file)
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = load_yaml(self.registry_file)

    def _sources(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = self._data.setdefault("stimuli", {})
        return result

    def _save(self) -> None:
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        save_yaml(self.registry_file, self._data)

    # ---- 注册 / CRUD ----

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
        }
        if spec.repo:
            entry["repo"] = {
                "name": spec.repo.name, "url": spec.repo.url,
                "ref": spec.repo.ref, "path": spec.repo.path,
            }
        self._sources()[spec.name] = entry
        self._save()
        logger.info("激励已注册: %s (type=%s)", spec.name, spec.source_type)
        return entry

    def get(self, name: str) -> StimulusSpec | None:
        """获取已注册激励源定义"""
        entry = self._sources().get(name)
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
        )

    def list_all(self) -> list[dict[str, Any]]:
        """列出所有已注册激励源"""
        return [{"name": k, **v} for k, v in self._sources().items()]

    def remove(self, name: str) -> bool:
        """移除激励注册"""
        sources = self._sources()
        if name not in sources:
            return False
        del sources[name]
        self._save()
        logger.info("激励已移除: %s", name)
        return True

    # ---- 获取 / 生成 ----

    def acquire(self, name: str, *, work_dir: str = "") -> StimulusArtifact:
        """根据激励源类型获取激励产物"""
        spec = self.get(name)
        if spec is None:
            raise CaseNotFoundError(f"激励不存在: {name}")

        dest = Path(work_dir) if work_dir else self.artifact_dir / name
        dest.mkdir(parents=True, exist_ok=True)

        artifact = StimulusArtifact(spec=spec)

        try:
            if spec.source_type == "repo":
                artifact = self._acquire_from_repo(spec, dest)
            elif spec.source_type == "generated":
                artifact = self._acquire_generated(spec, dest)
            elif spec.source_type == "stored":
                artifact = self._acquire_from_storage(spec, dest)
            elif spec.source_type == "external":
                artifact = self._acquire_from_url(spec, dest)
        except (OSError, RuntimeError, subprocess.SubprocessError) as e:
            artifact.status = "error"
            logger.error("激励获取失败 %s: %s", name, e)
            return artifact

        logger.info("激励就绪: %s -> %s", name, artifact.local_path)
        return artifact

    def _acquire_from_repo(self, spec: StimulusSpec, dest: Path) -> StimulusArtifact:
        """从代码仓检出激励"""
        if spec.repo is None or not spec.repo.url:
            raise ValidationError("repo 类型激励必须指定 repo.url")
        from framework.services.repo_service import RepoService
        svc = RepoService()
        ws = svc.checkout(spec.repo.name)
        return StimulusArtifact(
            spec=spec, local_path=ws.local_path,
            checksum=ws.commit_sha, status="ready" if ws.status != "error" else "error",
        )

    def _acquire_generated(self, spec: StimulusSpec, dest: Path) -> StimulusArtifact:
        """执行生成命令产出激励"""
        if not spec.generator_cmd:
            raise ValidationError("generated 类型激励必须指定 generator_cmd")
        r = subprocess.run(
            shlex.split(spec.generator_cmd),
            capture_output=True, text=True, cwd=str(dest), check=False,
        )
        if r.returncode != 0:
            raise RuntimeError(f"生成失败 (rc={r.returncode}): {r.stderr[:500]}")
        checksum = self._dir_checksum(dest)
        return StimulusArtifact(
            spec=spec, local_path=str(dest), checksum=checksum, status="ready",
        )

    def _acquire_from_storage(self, spec: StimulusSpec, dest: Path) -> StimulusArtifact:
        """从 Storage 获取激励"""
        if not spec.storage_key:
            raise ValidationError("stored 类型激励必须指定 storage_key")
        from framework.core.storage import create_storage
        storage = create_storage()
        data = storage.get("stimuli", spec.storage_key)
        if data is None:
            raise RuntimeError(f"Storage 中不存在: stimuli/{spec.storage_key}")
        # 将 data 写入本地文件
        import json
        out = dest / f"{spec.storage_key}.json"
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return StimulusArtifact(
            spec=spec, local_path=str(out), status="ready",
        )

    def _acquire_from_url(self, spec: StimulusSpec, dest: Path) -> StimulusArtifact:
        """从外部 URL 下载激励"""
        if not spec.external_url:
            raise ValidationError("external 类型激励必须指定 external_url")
        from framework.utils.net import validate_url_scheme
        validate_url_scheme(spec.external_url, context=f"stimulus {spec.name}")
        import urllib.request
        filename = spec.external_url.rstrip("/").split("/")[-1] or "stimulus_data"
        out = dest / filename
        urllib.request.urlretrieve(spec.external_url, str(out))  # nosec B310
        return StimulusArtifact(
            spec=spec, local_path=str(out), status="ready",
        )

    @staticmethod
    def _dir_checksum(path: Path) -> str:
        """对目录下所有文件计算简单 checksum"""
        h = hashlib.sha256()
        for f in sorted(path.rglob("*")):
            if f.is_file():
                h.update(f.read_bytes())
        return h.hexdigest()[:16]
