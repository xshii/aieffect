"""结果服务的数据模型

使用 dataclass 定义类型安全的返回值，替代 dict[str, Any]。

优势:
  - IDE 自动补全
  - 类型检查
  - 可以添加业务方法
  - 易于维护和重构
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any


# =========================================================================
# 对比相关模型
# =========================================================================


@dataclass
class RunInfo:
    """单次运行信息"""
    run_id: str
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（用于序列化）"""
        return asdict(self)


@dataclass
class CompareResult:
    """对比结果（成功）"""
    run_a: RunInfo
    run_b: RunInfo
    diffs: list[dict[str, str]]
    total_cases: int
    changed_cases: int

    def has_changes(self) -> bool:
        """是否有变更"""
        return self.changed_cases > 0

    def get_regression_count(self) -> int:
        """获取回归数量（从 passed 变为 failed）"""
        count = 0
        for diff in self.diffs:
            # 假设 diff 格式为 {"case": "name", "run_a_id": "passed", "run_b_id": "failed"}
            if len(diff) >= 3:
                values = list(diff.values())
                if len(values) >= 3 and "passed" in str(values[1]).lower() and "failed" in str(values[2]).lower():
                    count += 1
        return count

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            "run_a": self.run_a.to_dict(),
            "run_b": self.run_b.to_dict(),
            "diffs": self.diffs,
            "total_cases": self.total_cases,
            "changed_cases": self.changed_cases,
        }


@dataclass
class CompareError:
    """对比错误"""
    error: str

    def to_dict(self) -> dict[str, str]:
        """转换为字典（用于序列化）"""
        return {"error": self.error}


# CompareResponse 是两者的联合类型
CompareResponse = CompareResult | CompareError


# =========================================================================
# 上传相关模型
# =========================================================================


@dataclass
class UploadResult:
    """上传结果"""
    status: str  # "success" | "error"
    type: str    # "local" | "api" | "rsync"
    message: str = ""
    path: str = ""
    target: str = ""
    response: dict[str, Any] | None = None
    hint: str = ""

    @property
    def is_success(self) -> bool:
        """是否上传成功"""
        return self.status == "success"

    @property
    def is_error(self) -> bool:
        """是否上传失败"""
        return self.status == "error"

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（用于序列化）"""
        result: dict[str, Any] = {
            "status": self.status,
            "type": self.type,
        }
        if self.message:
            result["message"] = self.message
        if self.path:
            result["path"] = self.path
        if self.target:
            result["target"] = self.target
        if self.response is not None:
            result["response"] = self.response
        if self.hint:
            result["hint"] = self.hint
        return result


# =========================================================================
# 列表和汇总相关模型
# =========================================================================


@dataclass
class ResultSummary:
    """结果汇总统计"""
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    error: int = 0

    def to_dict(self) -> dict[str, int]:
        """转换为字典"""
        return asdict(self)


@dataclass
class ListResultsResponse:
    """列表结果响应"""
    summary: ResultSummary
    results: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            "summary": self.summary.to_dict(),
            "results": self.results,
        }


# =========================================================================
# 执行结果相关模型
# =========================================================================


@dataclass
class ExecuteResult:
    """命令执行结果"""
    returncode: int
    stdout: str
    stderr: str
    success: bool

    @property
    def is_success(self) -> bool:
        """是否执行成功"""
        return self.success

    @property
    def has_output(self) -> bool:
        """是否有标准输出"""
        return bool(self.stdout.strip())

    @property
    def has_error(self) -> bool:
        """是否有错误输出"""
        return bool(self.stderr.strip())

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（用于序列化）"""
        return asdict(self)


# =========================================================================
# 辅助函数
# =========================================================================


def dict_to_summary(data: dict[str, Any]) -> ResultSummary:
    """从字典创建 ResultSummary"""
    return ResultSummary(
        total=data.get("total", 0),
        passed=data.get("passed", 0),
        failed=data.get("failed", 0),
        skipped=data.get("skipped", 0),
        error=data.get("error", 0),
    )
