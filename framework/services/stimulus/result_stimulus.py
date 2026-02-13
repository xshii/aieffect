"""结果激励管理 - 从执行结果中获取激励数据

职责：
- 结果激励的注册、查询、列表、删除
- 通过 API 或二进制文件获取结果激励
"""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
from pathlib import Path
from typing import Any

from framework.core.exceptions import CaseNotFoundError, ValidationError
from framework.core.models import (
    ResultStimulusArtifact,
    ResultStimulusSpec,
    ResultStimulusType,
)

logger = logging.getLogger(__name__)


class ResultStimulusManager:
    """结果激励管理器"""

    def __init__(self, data: dict[str, Any], artifact_dir: str = "") -> None:
        """
        Args:
            data: 共享的配置数据字典（来自 YamlRegistry）
            artifact_dir: 产物保存目录
        """
        self._data = data
        if not artifact_dir:
            from framework.core.config import get_config
            artifact_dir = str(Path(get_config().workspace_dir) / "stimuli")
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

    def _result_stimuli_section(self) -> dict[str, dict[str, Any]]:
        """获取结果激励配置段"""
        result: dict[str, dict[str, Any]] = self._data.setdefault("result_stimuli", {})
        return result

    def _save(self) -> None:
        """保存配置数据（委托给父 Registry）"""
        # 注意：这里需要由门面类的 Registry 调用 _save()
        # 在门面类中会处理

    def register(self, spec: ResultStimulusSpec) -> dict[str, Any]:
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
        logger.info("结果激励已注册: %s (type=%s)", spec.name, spec.source_type)
        return entry

    def get(self, name: str) -> ResultStimulusSpec | None:
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

    def list_all(self) -> list[dict[str, Any]]:
        """列出所有结果激励"""
        return [{"name": k, **v} for k, v in self._result_stimuli_section().items()]

    def remove(self, name: str) -> bool:
        """移除结果激励"""
        rs = self._result_stimuli_section()
        if name not in rs:
            return False
        del rs[name]
        return True

    def collect(
        self, name: str, *, work_dir: str = "",
    ) -> ResultStimulusArtifact:
        """获取结果激励产物（通过 API 或读取二进制）"""
        spec = self.get(name)
        if spec is None:
            raise CaseNotFoundError(f"结果激励不存在: {name}")

        dest = Path(work_dir) if work_dir else self.artifact_dir / f"result_{name}"
        dest.mkdir(parents=True, exist_ok=True)

        try:
            if spec.source_type == ResultStimulusType.API:
                return self._collect_via_api(spec, dest)
            return self._collect_via_binary(spec, dest)
        except (OSError, RuntimeError, subprocess.SubprocessError) as e:
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
            raise RuntimeError(f"二进制文件不存在: {spec.binary_path}")

        out = dest / src.name
        out.write_bytes(src.read_bytes())

        data: dict[str, Any] = {}
        if spec.parser_cmd:
            r = subprocess.run(
                shlex.split(spec.parser_cmd),
                capture_output=True, text=True, cwd=str(dest), check=False,
            )
            if r.returncode != 0:
                raise RuntimeError(f"解析失败 (rc={r.returncode}): {r.stderr[:500]}")
            try:
                data = json.loads(r.stdout)
            except json.JSONDecodeError:
                data = {"raw_output": r.stdout[:2000]}

        return ResultStimulusArtifact(
            spec=spec, local_path=str(out), data=data, status="ready",
        )
