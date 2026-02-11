"""核心数据模型

所有核心数据类集中定义，消除 runner ↔ scheduler 的循环依赖。
其他模块统一从此处导入 Case / TaskResult / SuiteResult 及各领域实体。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# =========================================================================
# 原有模型
# =========================================================================


@dataclass
class Case:
    """单个测试用例定义"""

    name: str
    args: dict[str, str] = field(default_factory=dict)
    timeout: int = 3600  # 秒
    tags: list[str] = field(default_factory=list)
    environment: str = ""  # 绑定的执行环境
    params: dict[str, str] = field(default_factory=dict)  # 运行时参数
    repo: dict[str, str] = field(default_factory=dict)  # 外部仓库来源


@dataclass
class TaskResult:
    """单个测试用例的执行结果"""

    name: str
    status: str  # "passed", "failed", "error", "skipped"
    duration: float = 0.0  # 秒
    message: str = ""
    log_path: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)


def summarize_statuses(results: list[dict]) -> dict[str, int]:
    """统计结果状态分布（passed/failed/error），消除跨模块重复"""
    return {
        "total": len(results),
        "passed": sum(1 for r in results if r.get("status") == "passed"),
        "failed": sum(1 for r in results if r.get("status") == "failed"),
        "errors": sum(1 for r in results if r.get("status") == "error"),
    }


@dataclass
class SuiteResult:
    """测试套件执行结果汇总"""

    suite_name: str
    environment: str = ""
    snapshot_id: str = ""
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    results: list[TaskResult] = field(default_factory=list)

    @classmethod
    def from_tasks(
        cls,
        task_results: list[TaskResult],
        *,
        suite_name: str,
        environment: str = "",
        snapshot_id: str = "",
    ) -> SuiteResult:
        """从 TaskResult 列表构建 SuiteResult，自动统计状态"""
        return cls(
            suite_name=suite_name,
            environment=environment,
            snapshot_id=snapshot_id,
            total=len(task_results),
            passed=sum(1 for r in task_results if r.status == "passed"),
            failed=sum(1 for r in task_results if r.status == "failed"),
            errors=sum(1 for r in task_results if r.status == "error"),
            results=task_results,
        )

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.errors == 0


# =========================================================================
# 代码仓领域模型
# =========================================================================


@dataclass
class RepoSpec:
    """代码仓定义 — 支持 git / tar / api 三种来源

    source_type:
      - git: Git 仓库，通过 url + ref 检出
      - tar: tar 包，通过 tar_path（本地）或 tar_url（远程）解压
      - api: 通过 API 下载链接获取
    """

    name: str
    source_type: str = "git"   # git | tar | api

    # Git 来源
    url: str = ""
    ref: str = "main"
    path: str = ""             # 仓内子目录

    # Tar 来源
    tar_path: str = ""         # 本地 tar 包路径
    tar_url: str = ""          # 远程 tar 包 URL

    # API 来源
    api_url: str = ""          # API 下载地址
    api_token: str = ""        # API 认证令牌标识

    # 通用
    setup_cmd: str = ""        # 依赖安装命令
    build_cmd: str = ""        # 编译命令
    deps: list[str] = field(default_factory=list)   # 关联依赖包名列表
    credentials: str = ""      # 凭证标识


@dataclass
class CaseRepoBinding:
    """用例级代码仓绑定 — 不同用例可引用同一仓库的不同分支"""

    repo_name: str
    ref_override: str = ""     # 用例级分支覆盖（空则用仓库默认）
    shared: bool = True        # 是否复用已有工作目录（同 name+ref 共享）
    mount_point: str = ""      # 挂载点别名（用于多仓库场景）


@dataclass
class RepoWorkspace:
    """代码仓本地工作目录"""

    spec: RepoSpec
    local_path: str = ""
    commit_sha: str = ""
    status: str = "pending"    # pending | cloned | extracted | updated | error


# =========================================================================
# 环境领域模型
# =========================================================================


@dataclass
class ToolSpec:
    """EDA 工具定义"""

    name: str
    version: str
    install_path: str = ""
    env_vars: dict[str, str] = field(default_factory=dict)


@dataclass
class EnvironmentSpec:
    """执行环境定义"""

    name: str
    description: str = ""
    tools: dict[str, ToolSpec] = field(default_factory=dict)
    variables: dict[str, str] = field(default_factory=dict)
    licenses: dict[str, str] = field(default_factory=dict)


@dataclass
class EnvSession:
    """已装配的环境会话（可执行命令的运行时环境）"""

    environment: EnvironmentSpec
    resolved_vars: dict[str, str] = field(default_factory=dict)
    work_dir: str = ""
    status: str = "pending"  # pending | ready | torn_down | error


# =========================================================================
# 激励领域模型
# =========================================================================


@dataclass
class StimulusSpec:
    """激励源定义"""

    name: str
    source_type: str = "repo"  # repo | generated | stored | external
    repo: RepoSpec | None = None
    generator_cmd: str = ""    # 生成命令
    storage_key: str = ""      # 存储 key
    external_url: str = ""     # 外部地址
    description: str = ""


@dataclass
class StimulusArtifact:
    """已获取的激励产物"""

    spec: StimulusSpec
    local_path: str = ""
    checksum: str = ""
    status: str = "pending"  # pending | ready | error


# =========================================================================
# 构建领域模型
# =========================================================================


@dataclass
class BuildSpec:
    """构建配置"""

    name: str
    repo_name: str = ""       # 关联的代码仓
    setup_cmd: str = ""
    build_cmd: str = ""
    clean_cmd: str = ""
    output_dir: str = ""      # 构建产物输出目录（相对于 repo）


@dataclass
class BuildResult:
    """构建结果"""

    spec: BuildSpec
    output_path: str = ""
    status: str = "pending"  # pending | success | failed
    duration: float = 0.0
    message: str = ""


# =========================================================================
# 执行上下文
# =========================================================================


@dataclass
class ExecutionContext:
    """执行上下文 — 组合所有阶段产物，传递给执行器"""

    repos: list[RepoWorkspace] = field(default_factory=list)
    env_session: EnvSession | None = None
    builds: list[BuildResult] = field(default_factory=list)
    stimuli: list[StimulusArtifact] = field(default_factory=list)
    params: dict[str, str] = field(default_factory=dict)
