"""核心数据模型

所有核心数据类集中定义，消除 runner ↔ scheduler 的循环依赖。
其他模块统一从此处导入 Case / TaskResult / SuiteResult 及各领域实体。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
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
class TestMeta:
    """测试元信息 — 记录用例执行时的代码仓、环境等上下文"""

    repo_name: str = ""
    repo_ref: str = ""
    repo_commit: str = ""
    build_env: str = ""
    exe_env: str = ""
    stimulus_name: str = ""
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class ResultDataPath:
    """测试结果数据的获取路径配置"""

    log_path: str = ""           # 日志文件路径
    waveform_path: str = ""      # 波形文件路径
    coverage_path: str = ""      # 覆盖率数据路径
    report_path: str = ""        # 报告路径
    artifact_dir: str = ""       # 产物根目录
    custom_paths: dict[str, str] = field(default_factory=dict)


@dataclass
class TaskResult:
    """单个测试用例的执行结果"""

    name: str
    status: str  # "passed", "failed", "error", "skipped"
    duration: float = 0.0  # 秒
    message: str = ""
    log_path: str = ""
    meta: TestMeta | None = None
    result_paths: ResultDataPath | None = None


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

class BuildEnvType(str, Enum):
    """构建环境类型"""
    LOCAL = "local"
    REMOTE = "remote"


class ExeEnvType(str, Enum):
    """执行环境类型"""
    EDA = "eda"
    FPGA = "fpga"
    SILICON = "silicon"
    SAME_AS_BUILD = "same_as_build"


class EnvStatus(str, Enum):
    """环境会话状态"""
    PENDING = "pending"
    APPLIED = "applied"
    TIMEOUT = "timeout"
    RELEASED = "released"
    INVALID = "invalid"


@dataclass
class ToolSpec:
    """EDA 工具定义"""

    name: str
    version: str
    install_path: str = ""
    env_vars: dict[str, str] = field(default_factory=dict)


@dataclass
class BuildEnvSpec:
    """构建环境定义"""

    name: str
    build_env_type: str = BuildEnvType.LOCAL  # local | remote
    description: str = ""

    # 通用
    work_dir: str = ""             # 工作目录根路径
    variables: dict[str, str] = field(default_factory=dict)

    # remote 特有
    host: str = ""                 # 远端主机
    port: int = 22                 # SSH 端口
    user: str = ""                 # SSH 用户
    key_path: str = ""             # SSH 密钥路径


@dataclass
class ExeEnvSpec:
    """执行环境定义"""

    name: str
    exe_env_type: str = ExeEnvType.EDA  # eda | fpga | silicon | same_as_build
    description: str = ""

    # 通用
    api_url: str = ""              # Web API 地址（eda/fpga/silicon 用）
    api_token: str = ""            # API 认证令牌
    variables: dict[str, str] = field(default_factory=dict)
    tools: dict[str, ToolSpec] = field(default_factory=dict)
    licenses: dict[str, str] = field(default_factory=dict)
    timeout: int = 3600            # 默认超时（秒）

    # same_as_build 特有
    build_env_name: str = ""       # 引用的构建环境名称


@dataclass
class EnvSession:
    """环境会话 — apply 后获得，release 后失效

    生命周期: pending → applied → (timeout | released | invalid)
    """

    name: str
    build_env: BuildEnvSpec | None = None
    exe_env: ExeEnvSpec | None = None
    resolved_vars: dict[str, str] = field(default_factory=dict)
    work_dir: str = ""
    status: str = EnvStatus.PENDING
    session_id: str = ""
    message: str = ""


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
    # 构造参数
    params: dict[str, str] = field(default_factory=dict)
    template: str = ""         # 构造模板路径或内容


@dataclass
class StimulusArtifact:
    """已获取的激励产物"""

    spec: StimulusSpec
    local_path: str = ""
    checksum: str = ""
    status: str = "pending"  # pending | ready | error


class ResultStimulusType(str, Enum):
    """结果激励类型"""
    API = "api"
    BINARY = "binary"


@dataclass
class ResultStimulusSpec:
    """结果激励定义 — 从执行结果中提取的激励数据

    source_type:
      - api: 通过 API 获取执行后的结果激励
      - binary: 直接读取执行后产出的二进制文件
    """

    name: str
    source_type: str = ResultStimulusType.API  # api | binary
    api_url: str = ""          # API 地址（api 类型）
    api_token: str = ""        # API 认证令牌
    binary_path: str = ""      # 二进制文件路径（binary 类型）
    parser_cmd: str = ""       # 解析命令（对二进制做后处理）
    description: str = ""


@dataclass
class ResultStimulusArtifact:
    """已获取的结果激励产物"""

    spec: ResultStimulusSpec
    local_path: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"    # pending | ready | error
    message: str = ""


class TriggerType(str, Enum):
    """激励触发类型"""
    API = "api"
    BINARY = "binary"


@dataclass
class TriggerSpec:
    """激励触发定义

    trigger_type:
      - api: 通过 API 触发激励注入
      - binary: 通过执行二进制工具触发激励注入
    """

    name: str
    trigger_type: str = TriggerType.API  # api | binary
    api_url: str = ""          # API 地址（api 类型）
    api_token: str = ""        # API 认证令牌
    binary_cmd: str = ""       # 二进制执行命令（binary 类型）
    stimulus_name: str = ""    # 关联的激励名
    description: str = ""


@dataclass
class TriggerResult:
    """激励触发结果"""

    spec: TriggerSpec
    status: str = "pending"    # pending | success | failed
    message: str = ""
    response: dict[str, Any] = field(default_factory=dict)


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
    status: str = "pending"  # pending | success | failed | cached
    duration: float = 0.0
    message: str = ""
    repo_ref: str = ""        # 构建时使用的代码仓分支
    cached: bool = False      # 是否命中缓存


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
