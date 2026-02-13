"""激励服务 — 激励管理 / 构造 / 结果激励 / 触发

四大能力:
  1. 激励管理: 激励源 CRUD（repo / generated / stored / external）
  2. 激励构造: 基于模板 + 参数构建激励数据
  3. 结果激励管理: 从执行结果中获取激励（API / 二进制）
  4. 激励触发: 将激励注入到目标环境（API / 二进制工具）
"""

from __future__ import annotations

import hashlib
import json
import logging
import shlex
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from framework.services.repo_service import RepoService

from framework.core.exceptions import (
    CaseNotFoundError,
    ExecutionError,
    ResourceError,
    ValidationError,
)
from framework.core.models import (
    RepoSpec,
    ResultStimulusArtifact,
    ResultStimulusSpec,
    ResultStimulusType,
    StimulusArtifact,
    StimulusSpec,
    TriggerResult,
    TriggerSpec,
    TriggerType,
)
from framework.core.registry import YamlRegistry

logger = logging.getLogger(__name__)


class StimulusService(YamlRegistry):
    """激励全生命周期管理"""

    section_key = "stimuli"

    def __init__(
        self, registry_file: str, artifact_dir: str,
        repo_service: RepoService | None = None,
    ) -> None:
        super().__init__(registry_file)
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._repo_service = repo_service

    def _result_stimuli_section(self) -> dict[str, dict[str, Any]]:
        """获取结果激励配置段（从执行结果中提取的激励）"""
        result: dict[str, dict[str, Any]] = self._data.setdefault("result_stimuli", {})
        return result

    def _triggers_section(self) -> dict[str, dict[str, Any]]:
        """获取触发器配置段（激励注入方式定义）"""
        result: dict[str, dict[str, Any]] = self._data.setdefault("triggers", {})
        return result

    # =====================================================================
    # 1. 激励管理 — CRUD
    # =====================================================================

    @staticmethod
    def create_spec(data: dict[str, Any]) -> StimulusSpec:
        """从字典创建 StimulusSpec（CLI/Web 共用工厂）"""
        repo = None
        if data.get("repo"):
            r = data["repo"]
            repo = RepoSpec(
                name=r.get("name", data.get("name", "")),
                url=r.get("url", ""), ref=r.get("ref", "main"),
            )
        return StimulusSpec(
            name=data.get("name", ""),
            source_type=data.get("source_type", "repo"),
            repo=repo,
            generator_cmd=data.get("generator_cmd", ""),
            storage_key=data.get("storage_key", ""),
            external_url=data.get("external_url", ""),
            description=data.get("description", ""),
            params=data.get("params", {}),
            template=data.get("template", ""),
        )

    @staticmethod
    def create_result_stimulus_spec(data: dict[str, Any]) -> ResultStimulusSpec:
        """从字典创建 ResultStimulusSpec（CLI/Web 共用工厂）"""
        return ResultStimulusSpec(
            name=data.get("name", ""),
            source_type=data.get("source_type", ResultStimulusType.API),
            api_url=data.get("api_url", ""),
            api_token=data.get("api_token", ""),
            binary_path=data.get("binary_path", ""),
            parser_cmd=data.get("parser_cmd", ""),
            description=data.get("description", ""),
        )

    @staticmethod
    def create_trigger_spec(data: dict[str, Any]) -> TriggerSpec:
        """从字典创建 TriggerSpec（CLI/Web 共用工厂）"""
        return TriggerSpec(
            name=data.get("name", ""),
            trigger_type=data.get("trigger_type", TriggerType.API),
            api_url=data.get("api_url", ""),
            api_token=data.get("api_token", ""),
            binary_cmd=data.get("binary_cmd", ""),
            stimulus_name=data.get("stimulus_name", ""),
            description=data.get("description", ""),
        )

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
        return self._list_raw()

    def remove(self, name: str) -> bool:
        if not self._remove(name):
            return False
        logger.info("激励已移除: %s", name)
        return True

    # =====================================================================
    # 2. 激励获取 / 构造
    # =====================================================================

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
        except (OSError, ExecutionError, ResourceError, subprocess.SubprocessError) as e:
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
        spec = self.get(name)
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
        except (OSError, ExecutionError, ResourceError, subprocess.SubprocessError) as e:
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
            raise ExecutionError(f"构造失败 (rc={r.returncode}): {r.stderr[:500]}")
        checksum = self._dir_checksum(dest)
        return StimulusArtifact(
            spec=spec, local_path=str(dest), checksum=checksum, status="ready",
        )

    def _get_repo_service(self) -> RepoService:
        if self._repo_service is None:
            raise ValidationError("StimulusService 未注入 RepoService，请通过容器获取")
        return self._repo_service

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
            raise ExecutionError(f"生成失败 (rc={r.returncode}): {r.stderr[:500]}")
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
            raise ResourceError(f"Storage 中不存在: stimuli/{spec.storage_key}")
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

    # =====================================================================
    # 3. 结果激励管理 — 从执行结果中获取激励数据
    # =====================================================================

    def register_result_stimulus(self, spec: ResultStimulusSpec) -> dict[str, Any]:
        """注册结果激励"""
        if not spec.name:
            raise ValidationError("结果激励 name 为必填")
        if spec.source_type not in (ResultStimulusType.API, ResultStimulusType.BINARY):
            raise ValidationError(f"不支持的结果激励类型: {spec.source_type}")
        entry: dict[str, Any] = {
            "source_type": spec.source_type,
            "api_url": spec.api_url,
            "api_token": spec.api_token,
            "binary_path": spec.binary_path,
            "parser_cmd": spec.parser_cmd,
            "description": spec.description,
        }
        self._result_stimuli_section()[spec.name] = entry
        self._save()
        logger.info("结果激励已注册: %s (type=%s)", spec.name, spec.source_type)
        return entry

    def get_result_stimulus(self, name: str) -> ResultStimulusSpec | None:
        """获取结果激励定义"""
        entry = self._result_stimuli_section().get(name)
        if entry is None:
            return None
        return ResultStimulusSpec(
            name=name,
            source_type=entry.get("source_type", ResultStimulusType.API),
            api_url=entry.get("api_url", ""),
            api_token=entry.get("api_token", ""),
            binary_path=entry.get("binary_path", ""),
            parser_cmd=entry.get("parser_cmd", ""),
            description=entry.get("description", ""),
        )

    def list_result_stimuli(self) -> list[dict[str, Any]]:
        """列出所有结果激励"""
        return [{"name": k, **v} for k, v in self._result_stimuli_section().items()]

    def remove_result_stimulus(self, name: str) -> bool:
        """移除结果激励"""
        rs = self._result_stimuli_section()
        if name not in rs:
            return False
        del rs[name]
        self._save()
        return True

    def collect_result_stimulus(
        self, name: str, *, work_dir: str = "",
    ) -> ResultStimulusArtifact:
        """获取结果激励产物（通过 API 或读取二进制）"""
        spec = self.get_result_stimulus(name)
        if spec is None:
            raise CaseNotFoundError(f"结果激励不存在: {name}")

        dest = Path(work_dir) if work_dir else self.artifact_dir / f"result_{name}"
        dest.mkdir(parents=True, exist_ok=True)

        try:
            if spec.source_type == ResultStimulusType.API:
                return self._collect_via_api(spec, dest)
            return self._collect_via_binary(spec, dest)
        except (OSError, ExecutionError, ResourceError, subprocess.SubprocessError) as e:
            logger.error("结果激励获取失败 %s: %s", name, e)
            return ResultStimulusArtifact(
                spec=spec, status="error", message=str(e),
            )

    def _collect_via_api(
        self, spec: ResultStimulusSpec, dest: Path,
    ) -> ResultStimulusArtifact:
        """通过 API 获取结果激励"""
        if not spec.api_url:
            raise ValidationError("API 类型结果激励必须指定 api_url")
        from framework.utils.net import validate_url_scheme
        validate_url_scheme(spec.api_url, context=f"result_stimulus {spec.name}")
        import urllib.request
        req = urllib.request.Request(spec.api_url)
        if spec.api_token:
            req.add_header("Authorization", f"Bearer {spec.api_token}")
        with urllib.request.urlopen(req) as resp:  # nosec B310
            raw = resp.read().decode("utf-8")

        out = dest / f"{spec.name}_result.json"
        out.write_text(raw, encoding="utf-8")
        data: dict[str, Any] = {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            pass
        return ResultStimulusArtifact(
            spec=spec, local_path=str(out), data=data, status="ready",
        )

    def _collect_via_binary(
        self, spec: ResultStimulusSpec, dest: Path,
    ) -> ResultStimulusArtifact:
        """通过读取二进制文件获取结果激励"""
        if not spec.binary_path:
            raise ValidationError("binary 类型结果激励必须指定 binary_path")
        src = Path(spec.binary_path)
        if not src.exists():
            raise ResourceError(f"二进制文件不存在: {spec.binary_path}")

        out = dest / src.name
        out.write_bytes(src.read_bytes())

        data: dict[str, Any] = {}
        if spec.parser_cmd:
            r = subprocess.run(
                shlex.split(spec.parser_cmd),
                capture_output=True, text=True, cwd=str(dest), check=False,
            )
            if r.returncode != 0:
                raise ExecutionError(f"解析失败 (rc={r.returncode}): {r.stderr[:500]}")
            try:
                data = json.loads(r.stdout)
            except json.JSONDecodeError:
                data = {"raw_output": r.stdout[:2000]}

        return ResultStimulusArtifact(
            spec=spec, local_path=str(out), data=data, status="ready",
        )

    # =====================================================================
    # 4. 激励触发 — 将激励注入到目标环境
    # =====================================================================

    def register_trigger(self, spec: TriggerSpec) -> dict[str, Any]:
        """注册激励触发器"""
        if not spec.name:
            raise ValidationError("触发器 name 为必填")
        if spec.trigger_type not in (TriggerType.API, TriggerType.BINARY):
            raise ValidationError(f"不支持的触发类型: {spec.trigger_type}")
        entry: dict[str, Any] = {
            "trigger_type": spec.trigger_type,
            "api_url": spec.api_url,
            "api_token": spec.api_token,
            "binary_cmd": spec.binary_cmd,
            "stimulus_name": spec.stimulus_name,
            "description": spec.description,
        }
        self._triggers_section()[spec.name] = entry
        self._save()
        logger.info("触发器已注册: %s (type=%s)", spec.name, spec.trigger_type)
        return entry

    def get_trigger(self, name: str) -> TriggerSpec | None:
        """获取触发器定义"""
        entry = self._triggers_section().get(name)
        if entry is None:
            return None
        return TriggerSpec(
            name=name,
            trigger_type=entry.get("trigger_type", TriggerType.API),
            api_url=entry.get("api_url", ""),
            api_token=entry.get("api_token", ""),
            binary_cmd=entry.get("binary_cmd", ""),
            stimulus_name=entry.get("stimulus_name", ""),
            description=entry.get("description", ""),
        )

    def list_triggers(self) -> list[dict[str, Any]]:
        """列出所有触发器"""
        return [{"name": k, **v} for k, v in self._triggers_section().items()]

    def remove_trigger(self, name: str) -> bool:
        """移除触发器"""
        trigs = self._triggers_section()
        if name not in trigs:
            return False
        del trigs[name]
        self._save()
        return True

    def trigger(
        self, name: str, *,
        stimulus_path: str = "",
        payload: dict[str, Any] | None = None,
    ) -> TriggerResult:
        """触发激励注入

        Args:
            name: 触发器名称
            stimulus_path: 激励文件路径（可选，覆盖自动获取）
            payload: 额外载荷数据（API 类型附加到请求体）
        """
        spec = self.get_trigger(name)
        if spec is None:
            raise CaseNotFoundError(f"触发器不存在: {name}")

        if not stimulus_path and spec.stimulus_name:
            art = self.acquire(spec.stimulus_name)
            if art.status != "ready":
                return TriggerResult(
                    spec=spec, status="failed",
                    message=f"关联激励获取失败: {spec.stimulus_name}",
                )
            stimulus_path = art.local_path

        try:
            if spec.trigger_type == TriggerType.API:
                return self._trigger_via_api(spec, stimulus_path, payload)
            return self._trigger_via_binary(spec, stimulus_path)
        except (OSError, ExecutionError, ResourceError, subprocess.SubprocessError) as e:
            logger.error("激励触发失败 %s: %s", name, e)
            return TriggerResult(
                spec=spec, status="failed", message=str(e),
            )

    def _trigger_via_api(
        self, spec: TriggerSpec, stimulus_path: str,
        payload: dict[str, Any] | None,
    ) -> TriggerResult:
        """通过 API 触发激励"""
        if not spec.api_url:
            raise ValidationError("API 触发器必须指定 api_url")
        from framework.utils.net import validate_url_scheme
        validate_url_scheme(spec.api_url, context=f"trigger {spec.name}")

        import urllib.request
        body: dict[str, Any] = {**(payload or {})}
        if stimulus_path:
            body["stimulus_path"] = stimulus_path
            p = Path(stimulus_path)
            if p.is_file() and p.suffix == ".json":
                try:
                    body["stimulus_data"] = json.loads(
                        p.read_text(encoding="utf-8"),
                    )
                except json.JSONDecodeError:
                    pass

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            spec.api_url, data=data, method="POST",
            headers={"Content-Type": "application/json"},
        )
        if spec.api_token:
            req.add_header("Authorization", f"Bearer {spec.api_token}")
        with urllib.request.urlopen(req) as resp:  # nosec B310
            resp_data = json.loads(resp.read().decode("utf-8"))

        logger.info("API 触发成功: %s", spec.name)
        return TriggerResult(
            spec=spec, status="success", response=resp_data,
        )

    def _trigger_via_binary(
        self, spec: TriggerSpec, stimulus_path: str,
    ) -> TriggerResult:
        """通过二进制工具触发激励"""
        if not spec.binary_cmd:
            raise ValidationError("binary 触发器必须指定 binary_cmd")
        cmd = spec.binary_cmd
        if stimulus_path:
            cmd = f"{cmd} {stimulus_path}"
        r = subprocess.run(
            shlex.split(cmd), capture_output=True, text=True, check=False,
        )
        if r.returncode != 0:
            raise ExecutionError(f"触发失败 (rc={r.returncode}): {r.stderr[:500]}")

        response: dict[str, Any] = {"stdout": r.stdout[:2000]}
        try:
            response = json.loads(r.stdout)
        except json.JSONDecodeError:
            pass

        logger.info("binary 触发成功: %s", spec.name)
        return TriggerResult(
            spec=spec, status="success", response=response,
        )

    @staticmethod
    def _dir_checksum(path: Path) -> str:
        """对目录下所有文件计算简单 checksum"""
        h = hashlib.sha256()
        for f in sorted(path.rglob("*")):
            if f.is_file():
                h.update(f.read_bytes())
        return h.hexdigest()[:16]
