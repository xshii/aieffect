"""环境服务 — 执行环境注册 / 装配 / 交互 / 回收

管理 EDA 工具链、环境变量、许可证等环境资源，
提供「装配 → 交互 → 回收」的环境会话生命周期。
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from framework.core.exceptions import CaseNotFoundError, ValidationError
from framework.core.models import EnvironmentSpec, EnvSession, ToolSpec
from framework.utils.yaml_io import load_yaml, save_yaml

logger = logging.getLogger(__name__)


class EnvService:
    """执行环境生命周期管理"""

    def __init__(self, registry_file: str = "") -> None:
        if not registry_file:
            from framework.core.config import get_config
            registry_file = getattr(get_config(), "envs_file", "data/environments.yml")
        self.registry_file = Path(registry_file)
        self._data: dict[str, Any] = load_yaml(self.registry_file)

    def _envs(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = self._data.setdefault("environments", {})
        return result

    def _save(self) -> None:
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        save_yaml(self.registry_file, self._data)

    # ---- 注册 / CRUD ----

    def register(self, spec: EnvironmentSpec) -> dict[str, Any]:
        """注册执行环境"""
        if not spec.name:
            raise ValidationError("环境 name 为必填")
        tools_dict: dict[str, dict[str, Any]] = {}
        for tname, tool in spec.tools.items():
            tools_dict[tname] = {
                "version": tool.version,
                "install_path": tool.install_path,
                "env_vars": tool.env_vars,
            }
        entry: dict[str, Any] = {
            "description": spec.description,
            "tools": tools_dict,
            "variables": spec.variables,
            "licenses": spec.licenses,
        }
        self._envs()[spec.name] = entry
        self._save()
        logger.info("环境已注册: %s", spec.name)
        return entry

    def get(self, name: str) -> EnvironmentSpec | None:
        """获取已注册环境定义"""
        entry = self._envs().get(name)
        if entry is None:
            return None
        tools: dict[str, ToolSpec] = {}
        for tname, tinfo in (entry.get("tools") or {}).items():
            ti = tinfo if isinstance(tinfo, dict) else {}
            tools[tname] = ToolSpec(
                name=tname,
                version=ti.get("version", ""),
                install_path=ti.get("install_path", ""),
                env_vars=ti.get("env_vars", {}),
            )
        return EnvironmentSpec(
            name=name,
            description=entry.get("description", ""),
            tools=tools,
            variables=entry.get("variables", {}),
            licenses=entry.get("licenses", {}),
        )

    def list_all(self) -> list[dict[str, Any]]:
        """列出所有已注册环境"""
        return [{"name": k, **v} for k, v in self._envs().items()]

    def remove(self, name: str) -> bool:
        """移除环境注册"""
        envs = self._envs()
        if name not in envs:
            return False
        del envs[name]
        self._save()
        logger.info("环境已移除: %s", name)
        return True

    # ---- 装配 / 交互 / 回收 ----

    def provision(self, name: str, *, work_dir: str = "") -> EnvSession:
        """装配环境：解析工具路径、拼合环境变量，返回可用的会话"""
        spec = self.get(name)
        if spec is None:
            raise CaseNotFoundError(f"环境不存在: {name}")

        resolved: dict[str, str] = {}

        # 1. 许可证变量
        for lic_name, lic_value in spec.licenses.items():
            resolved[lic_name] = lic_value

        # 2. 工具链路径 + 工具自带环境变量
        path_parts: list[str] = []
        for tool in spec.tools.values():
            if tool.install_path:
                bin_path = str(Path(tool.install_path) / "bin")
                path_parts.append(bin_path)
            for vk, vv in tool.env_vars.items():
                resolved[vk] = vv.replace("{version}", tool.version).replace(
                    "{install_path}", tool.install_path
                )

        # 3. 用户自定义变量
        for vk, vv in spec.variables.items():
            resolved[vk] = vv

        # 4. PATH 追加
        if path_parts:
            existing = os.environ.get("PATH", "")
            resolved["PATH"] = ":".join(path_parts) + (":" + existing if existing else "")

        if not work_dir:
            from framework.core.config import get_config
            work_dir = str(Path(get_config().workspace_dir) / f"env_{name}")
        Path(work_dir).mkdir(parents=True, exist_ok=True)

        session = EnvSession(
            environment=spec,
            resolved_vars=resolved,
            work_dir=work_dir,
            status="ready",
        )
        logger.info("环境已装配: %s (%d 个变量, work_dir=%s)", name, len(resolved), work_dir)
        return session

    def execute_in(
        self, session: EnvSession, cmd: str, *, timeout: int = 3600,
    ) -> dict[str, Any]:
        """在已装配的环境会话中执行命令"""
        if session.status != "ready":
            raise ValidationError(f"环境会话状态不可用: {session.status}")

        env = {**os.environ, **session.resolved_vars}
        logger.info("执行命令: %s (env=%s)", cmd, session.environment.name)

        try:
            result = subprocess.run(
                shlex.split(cmd),
                capture_output=True, text=True, timeout=timeout,
                cwd=session.work_dir, env=env, check=False,
            )
            return {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": f"命令超时 ({timeout}s)",
                "success": False,
            }

    def teardown(self, session: EnvSession) -> None:
        """回收环境会话"""
        session.status = "torn_down"
        logger.info("环境已回收: %s", session.environment.name)
