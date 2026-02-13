"""激励构造器 - 激励获取与构造

职责：
- 从不同来源获取激励（repo / generated / stored / external）
- 基于模板 + 参数构造激励数据
"""

from __future__ import annotations

import hashlib
import json
import logging
import shlex
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from framework.services.repo_service import RepoService
    from framework.services.stimulus.registry import StimulusRegistry

from framework.core.exceptions import CaseNotFoundError, ValidationError
from framework.core.models import StimulusArtifact, StimulusSpec

logger = logging.getLogger(__name__)


class StimulusConstructor:
    """激励构造器"""

    def __init__(
        self,
        registry: StimulusRegistry,
        artifact_dir: str = "",
        repo_service: RepoService | None = None,
    ) -> None:
        if not artifact_dir:
            from framework.core.config import get_config
            artifact_dir = str(Path(get_config().workspace_dir) / "stimuli")
        self.registry = registry
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._repo_service = repo_service

    def acquire(self, name: str, *, work_dir: str = "") -> StimulusArtifact:
        """根据激励源类型获取激励产物"""
        spec = self.registry.get(name)
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

    def construct(
        self, name: str, *,
        params: dict[str, str] | None = None,
        work_dir: str = "",
    ) -> StimulusArtifact:
        """构造激励 — 基于模板 + 参数生成激励数据

        构造流程:
          1. 读取激励定义中的 template 和默认 params
          2. 合并用户传入的 params（优先级更高）
          3. 渲染模板或执行 generator_cmd（注入参数为环境变量）
          4. 返回构造产物
        """
        spec = self.registry.get(name)
        if spec is None:
            raise CaseNotFoundError(f"激励不存在: {name}")

        dest = Path(work_dir) if work_dir else self.artifact_dir / f"{name}_constructed"
        dest.mkdir(parents=True, exist_ok=True)

        merged_params = {**spec.params, **(params or {})}

        try:
            if spec.template:
                artifact = self._construct_from_template(spec, merged_params, dest)
            elif spec.generator_cmd:
                artifact = self._construct_with_cmd(spec, merged_params, dest)
            else:
                raise ValidationError("构造激励需要 template 或 generator_cmd")
        except (OSError, RuntimeError, subprocess.SubprocessError) as e:
            logger.error("激励构造失败 %s: %s", name, e)
            return StimulusArtifact(spec=spec, status="error")

        logger.info("激励已构造: %s -> %s", name, artifact.local_path)
        return artifact

    def _construct_from_template(
        self, spec: StimulusSpec, params: dict[str, str], dest: Path,
    ) -> StimulusArtifact:
        """从模板构造激励"""
        template_path = Path(spec.template)
        if template_path.is_file():
            content = template_path.read_text(encoding="utf-8")
        else:
            content = spec.template

        for key, value in params.items():
            content = content.replace(f"${{{key}}}", value)
            content = content.replace(f"$({key})", value)

        out = dest / f"{spec.name}_stimulus.txt"
        out.write_text(content, encoding="utf-8")
        checksum = hashlib.sha256(content.encode()).hexdigest()[:16]
        return StimulusArtifact(
            spec=spec, local_path=str(out), checksum=checksum, status="ready",
        )

    def _construct_with_cmd(
        self, spec: StimulusSpec, params: dict[str, str], dest: Path,
    ) -> StimulusArtifact:
        """通过命令构造激励（参数注入为环境变量）"""
        import os
        env = {**os.environ, **{f"STIM_{k.upper()}": v for k, v in params.items()}}
        r = subprocess.run(
            shlex.split(spec.generator_cmd),
            capture_output=True, text=True, cwd=str(dest),
            env=env, check=False,
        )
        if r.returncode != 0:
            raise RuntimeError(f"构造失败 (rc={r.returncode}): {r.stderr[:500]}")
        checksum = self._dir_checksum(dest)
        return StimulusArtifact(
            spec=spec, local_path=str(dest), checksum=checksum, status="ready",
        )

    def _get_repo_service(self) -> RepoService:
        if self._repo_service is not None:
            return self._repo_service
        from framework.services.repo_service import RepoService
        return RepoService()

    def _acquire_from_repo(self, spec: StimulusSpec, dest: Path) -> StimulusArtifact:
        """从代码仓检出激励"""
        if spec.repo is None or not spec.repo.url:
            raise ValidationError("repo 类型激励必须指定 repo.url")
        svc = self._get_repo_service()
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
