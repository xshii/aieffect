"""服务容器 — 统一依赖注入，消除跨服务裸构造

所有服务通过容器获取，同一容器内的服务实例共享状态（缓存等）。

用法:
    container = ServiceContainer()
    build_svc = container.build          # 懒加载
    repo_svc  = container.repo           # 同容器共享
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from framework.services.build_service import BuildService
    from framework.services.env_service import EnvService
    from framework.services.repo_service import RepoService
    from framework.services.result_service import ResultService
    from framework.services.run_service import RunService
    from framework.services.stimulus_service import StimulusService

logger = logging.getLogger(__name__)


class ServiceContainer:
    """懒加载服务容器 — 每个实例持有一组共享的服务"""

    def __init__(self) -> None:
        self._instances: dict[str, object] = {}

    @property
    def repo(self) -> RepoService:
        if "repo" not in self._instances:
            from framework.services.repo_service import RepoService
            self._instances["repo"] = RepoService()
        return self._instances["repo"]  # type: ignore[return-value]

    @property
    def build(self) -> BuildService:
        if "build" not in self._instances:
            from framework.services.build_service import BuildService
            self._instances["build"] = BuildService()
        return self._instances["build"]  # type: ignore[return-value]

    @property
    def stimulus(self) -> StimulusService:
        if "stimulus" not in self._instances:
            from framework.services.stimulus_service import StimulusService
            self._instances["stimulus"] = StimulusService()
        return self._instances["stimulus"]  # type: ignore[return-value]

    @property
    def env(self) -> EnvService:
        if "env" not in self._instances:
            from framework.services.env_service import EnvService
            self._instances["env"] = EnvService()
        return self._instances["env"]  # type: ignore[return-value]

    @property
    def result(self) -> ResultService:
        if "result" not in self._instances:
            from framework.services.result_service import ResultService
            self._instances["result"] = ResultService()
        return self._instances["result"]  # type: ignore[return-value]

    @property
    def run(self) -> RunService:
        if "run" not in self._instances:
            from framework.services.run_service import RunService
            self._instances["run"] = RunService()
        return self._instances["run"]  # type: ignore[return-value]
