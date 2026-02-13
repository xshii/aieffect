"""激励服务 - 门面类（Facade Pattern）

职责：
- 统一对外接口，整合所有激励相关功能
- 保持向后兼容性
- 代理到各个子模块

重构说明：
- 原 585 行单体类拆分为 4 个模块
- 使用门面模式保持接口不变
- 降低复杂度，提高可维护性
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from framework.services.repo_service import RepoService

from framework.core.models import (
    ResultStimulusArtifact,
    ResultStimulusSpec,
    StimulusArtifact,
    StimulusSpec,
    TriggerResult,
    TriggerSpec,
)
from framework.services.stimulus import (
    ResultStimulusManager,
    StimulusConstructor,
    StimulusRegistry,
    TriggerManager,
)


class StimulusService(StimulusRegistry):
    """激励全生命周期管理 - 门面类

    整合 4 大能力:
      1. 激励管理: 激励源 CRUD（registry）
      2. 激励构造: 基于模板 + 参数构建激励数据（constructor）
      3. 结果激励管理: 从执行结果中获取激励（result_stimulus）
      4. 激励触发: 将激励注入到目标环境（trigger）
    """

    def __init__(
        self, registry_file: str = "", artifact_dir: str = "",
        repo_service: RepoService | None = None,
    ) -> None:
        super().__init__(registry_file)

        # 初始化 artifact_dir
        if not artifact_dir:
            from framework.core.config import get_config
            artifact_dir = str(Path(get_config().workspace_dir) / "stimuli")

        # 初始化各个管理器
        self._constructor = StimulusConstructor(
            registry=self, artifact_dir=artifact_dir, repo_service=repo_service,
        )
        self._result_stimulus = ResultStimulusManager(
            data=self._data, artifact_dir=artifact_dir,
        )
        self._trigger = TriggerManager(
            data=self._data, constructor=self._constructor,
        )

    # =====================================================================
    # 1. 激励管理 — CRUD（继承自 StimulusRegistry）
    # =====================================================================
    # register(), get(), list_all(), remove() 已由父类 StimulusRegistry 提供

    # =====================================================================
    # 2. 激励获取 / 构造（代理到 StimulusConstructor）
    # =====================================================================

    def acquire(self, name: str, *, work_dir: str = "") -> StimulusArtifact:
        """根据激励源类型获取激励产物"""
        return self._constructor.acquire(name, work_dir=work_dir)

    def construct(
        self, name: str, *,
        params: dict[str, str] | None = None,
        work_dir: str = "",
    ) -> StimulusArtifact:
        """构造激励 — 基于模板 + 参数生成激励数据"""
        return self._constructor.construct(name, params=params, work_dir=work_dir)

    # =====================================================================
    # 3. 结果激励管理（代理到 ResultStimulusManager）
    # =====================================================================

    def register_result_stimulus(self, spec: ResultStimulusSpec) -> dict[str, Any]:
        """注册结果激励"""
        result = self._result_stimulus.register(spec)
        self._save()  # 保存配置
        return result

    def get_result_stimulus(self, name: str) -> ResultStimulusSpec | None:
        """获取结果激励定义"""
        return self._result_stimulus.get(name)

    def list_result_stimuli(self) -> list[dict[str, Any]]:
        """列出所有结果激励"""
        return self._result_stimulus.list_all()

    def remove_result_stimulus(self, name: str) -> bool:
        """移除结果激励"""
        result = self._result_stimulus.remove(name)
        if result:
            self._save()  # 保存配置
        return result

    def collect_result_stimulus(
        self, name: str, *, work_dir: str = "",
    ) -> ResultStimulusArtifact:
        """获取结果激励产物（通过 API 或读取二进制）"""
        return self._result_stimulus.collect(name, work_dir=work_dir)

    # =====================================================================
    # 4. 激励触发（代理到 TriggerManager）
    # =====================================================================

    def register_trigger(self, spec: TriggerSpec) -> dict[str, Any]:
        """注册激励触发器"""
        result = self._trigger.register(spec)
        self._save()  # 保存配置
        return result

    def get_trigger(self, name: str) -> TriggerSpec | None:
        """获取触发器定义"""
        return self._trigger.get(name)

    def list_triggers(self) -> list[dict[str, Any]]:
        """列出所有触发器"""
        return self._trigger.list_all()

    def remove_trigger(self, name: str) -> bool:
        """移除触发器"""
        result = self._trigger.remove(name)
        if result:
            self._save()  # 保存配置
        return result

    def trigger(
        self, name: str, *,
        stimulus_path: str = "",
        payload: dict[str, Any] | None = None,
    ) -> TriggerResult:
        """触发激励注入"""
        return self._trigger.trigger(name, stimulus_path=stimulus_path, payload=payload)
