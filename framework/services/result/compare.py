"""结果对比 - 对比两次执行结果的差异

职责：
- 对比两次执行结果
- 找到变化的用例
- 计算差异统计
"""

from __future__ import annotations

from typing import Any

from framework.core.history import HistoryManager
from framework.core.result_models import CompareError, CompareResponse, CompareResult, RunInfo


class ResultCompare:
    """结果对比管理器"""

    def __init__(self, history: HistoryManager | None = None) -> None:
        self.history = history or HistoryManager()

    def compare_runs(self, run_id_a: str, run_id_b: str) -> CompareResponse:
        """对比两次执行结果"""
        # 输入验证
        if not run_id_a or not run_id_b:
            return CompareError(error="run_id 不能为空")
        if run_id_a == run_id_b:
            return CompareError(error="不能对比相同的 run_id")

        # 查找记录
        rec_a, rec_b = self._find_records(run_id_a, run_id_b)
        if rec_a is None or rec_b is None:
            missing = [
                rid for rid, rec in ((run_id_a, rec_a), (run_id_b, rec_b))
                if rec is None
            ]
            return CompareError(error=f"未找到记录: {', '.join(missing)}")

        # 计算差异
        diffs, total = self._compute_diffs(rec_a, rec_b, run_id_a, run_id_b)
        return CompareResult(
            run_a=RunInfo(run_id=run_id_a, summary=rec_a.get("summary", {})),
            run_b=RunInfo(run_id=run_id_b, summary=rec_b.get("summary", {})),
            diffs=diffs,
            total_cases=total,
            changed_cases=len(diffs),
        )

    def _find_records(
        self, run_id_a: str, run_id_b: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """查找两个 run_id 对应的记录"""
        all_records = self.history.query(limit=10000)
        rec_a: dict[str, Any] | None = None
        rec_b: dict[str, Any] | None = None
        for r in all_records:
            rid = r.get("run_id")
            if rid == run_id_a:
                rec_a = r
            elif rid == run_id_b:
                rec_b = r
            if rec_a is not None and rec_b is not None:
                break
        return rec_a, rec_b

    @staticmethod
    def _compute_diffs(
        rec_a: dict[str, Any], rec_b: dict[str, Any],
        run_id_a: str, run_id_b: str,
    ) -> tuple[list[dict[str, str]], int]:
        """计算两次执行的差异"""
        cases_a = {r["name"]: r for r in rec_a.get("results", [])}
        cases_b = {r["name"]: r for r in rec_b.get("results", [])}
        all_names = sorted(set(cases_a) | set(cases_b))
        diffs: list[dict[str, str]] = []
        for name in all_names:
            a_status = cases_a.get(name, {}).get("status", "—")
            b_status = cases_b.get(name, {}).get("status", "—")
            if a_status != b_status:
                diffs.append(
                    {"case": name, run_id_a: a_status, run_id_b: b_status},
                )
        return diffs, len(all_names)
