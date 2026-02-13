"""领域协议定义

集中定义框架各层之间的接口契约（Protocol），
实现依赖倒置 — 上层依赖抽象而非具体实现。

使用 typing.Protocol 而非 ABC，使得现有类无需修改继承关系即可满足协议。
"""

from __future__ import annotations

from typing import Any, Protocol


# =========================================================================
# 环境管理协议
# =========================================================================

class EnvironmentProvider(Protocol):
    """环境资源提供者协议

    抽象环境的 apply/release 生命周期，
    使调度器和编排器不依赖 EnvService 具体实现。
    """

    def apply(
        self, *, build_env_name: str = "", exe_env_name: str = "",
    ) -> Any:
        """申请环境资源，返回 session 对象"""
        ...

    def release(self, session: Any) -> Any:
        """释放环境资源"""
        ...

    def execute_in(
        self, session: Any, cmd: str, *, timeout: int = 3600,
    ) -> dict[str, Any]:
        """在环境中执行命令"""
        ...


# =========================================================================
# 代码仓管理协议
# =========================================================================

class RepoProvider(Protocol):
    """代码仓提供者协议

    抽象代码仓的 checkout/list 操作，
    使构建服务和编排器不依赖 RepoService 具体实现。
    """

    def checkout(
        self, name: str, *, ref_override: str = "",
    ) -> Any:
        """检出代码仓到本地，返回 workspace 对象"""
        ...

    def get(self, name: str) -> Any | None:
        """获取代码仓定义"""
        ...

    def list_all(self) -> list[dict[str, Any]]:
        """列出所有已注册代码仓"""
        ...


# =========================================================================
# 构建协议
# =========================================================================

class BuildProvider(Protocol):
    """构建提供者协议"""

    def build(
        self, name: str, *,
        work_dir: str = "",
        repo_ref: str = "",
        force: bool = False,
    ) -> Any:
        """执行构建流程，返回 BuildResult"""
        ...

    def get(self, name: str) -> Any | None:
        """获取构建定义"""
        ...


# =========================================================================
# 激励协议
# =========================================================================

class StimulusProvider(Protocol):
    """激励提供者协议"""

    def acquire(self, name: str, *, work_dir: str = "") -> Any:
        """获取激励产物"""
        ...

    def construct(
        self, name: str, *,
        params: dict[str, str] | None = None,
    ) -> Any:
        """构造激励"""
        ...


# =========================================================================
# 结果格式化协议
# =========================================================================

class ResultFormatter(Protocol):
    """结果格式化器协议

    实现此协议即可扩展报告输出格式（HTML、JSON、JUnit XML 等）。
    """

    def format(self, results: list[dict[str, Any]]) -> str:
        """将结果数据格式化为字符串"""
        ...

    def extension(self) -> str:
        """返回输出文件扩展名（如 '.html'）"""
        ...


# =========================================================================
# 历史存储协议
# =========================================================================

class HistoryStore(Protocol):
    """执行历史存储协议

    抽象历史记录的读写，使 ResultService/Pipeline 不绑定 JSON 文件实现。
    可替换为数据库、远程 API 等后端。
    """

    def record_run(
        self, *,
        suite: str,
        results: list[dict[str, Any]],
        environment: str = "",
        snapshot_id: str = "",
        params: dict[str, str] | None = None,
        meta: dict[str, Any] | None = None,
        result_paths: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """记录一次执行，返回含 run_id 的记录"""
        ...

    def query(
        self, *,
        suite: str | None = None,
        environment: str | None = None,
        case_name: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """查询执行历史"""
        ...

    def case_summary(self, case_name: str) -> dict[str, Any]:
        """获取单个用例的历史汇总"""
        ...


# =========================================================================
# 快照存储协议
# =========================================================================

class SnapshotStore(Protocol):
    """版本快照存储协议

    抽象快照的 CRUD 操作，使编排器和 CLI 不绑定文件系统实现。
    可替换为数据库、对象存储等后端。
    """

    def create(
        self, description: str = "", snapshot_id: str | None = None,
    ) -> dict[str, Any]:
        """创建版本快照，返回快照数据"""
        ...

    def get(self, snapshot_id: str) -> dict[str, Any] | None:
        """获取指定快照的完整内容"""
        ...

    def list_snapshots(self) -> list[dict[str, Any]]:
        """列出所有快照摘要"""
        ...

    def restore(self, snapshot_id: str) -> bool:
        """恢复指定快照到当前清单"""
        ...
