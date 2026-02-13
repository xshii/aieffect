"""激励触发器 - 将激励注入到目标环境

职责：
- 触发器的注册、查询、列表、删除
- 通过 API 或二进制工具触发激励注入
"""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from framework.services.stimulus.constructor import StimulusConstructor

from framework.core.exceptions import CaseNotFoundError, ValidationError
from framework.core.models import TriggerResult, TriggerSpec, TriggerType

logger = logging.getLogger(__name__)


class TriggerManager:
    """激励触发器管理器"""

    def __init__(
        self,
        data: dict[str, Any],
        constructor: StimulusConstructor | None = None,
    ) -> None:
        """
        Args:
            data: 共享的配置数据字典（来自 YamlRegistry）
            constructor: 激励构造器（用于自动获取关联激励）
        """
        self._data = data
        self._constructor = constructor

    def _triggers_section(self) -> dict[str, dict[str, Any]]:
        """获取触发器配置段"""
        result: dict[str, dict[str, Any]] = self._data.setdefault("triggers", {})
        return result

    def register(self, spec: TriggerSpec) -> dict[str, Any]:
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
        logger.info("触发器已注册: %s (type=%s)", spec.name, spec.trigger_type)
        return entry

    def get(self, name: str) -> TriggerSpec | None:
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

    def list_all(self) -> list[dict[str, Any]]:
        """列出所有触发器"""
        return [{"name": k, **v} for k, v in self._triggers_section().items()]

    def remove(self, name: str) -> bool:
        """移除触发器"""
        trigs = self._triggers_section()
        if name not in trigs:
            return False
        del trigs[name]
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
        spec = self.get(name)
        if spec is None:
            raise CaseNotFoundError(f"触发器不存在: {name}")

        if not stimulus_path and spec.stimulus_name:
            if self._constructor is None:
                return TriggerResult(
                    spec=spec, status="failed",
                    message="无法获取关联激励：未提供 constructor",
                )
            art = self._constructor.acquire(spec.stimulus_name)
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
        except (OSError, RuntimeError, subprocess.SubprocessError) as e:
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
            raise RuntimeError(f"触发失败 (rc={r.returncode}): {r.stderr[:500]}")

        response: dict[str, Any] = {"stdout": r.stdout[:2000]}
        try:
            response = json.loads(r.stdout)
        except json.JSONDecodeError:
            pass

        logger.info("binary 触发成功: %s", spec.name)
        return TriggerResult(
            spec=spec, status="success", response=response,
        )
