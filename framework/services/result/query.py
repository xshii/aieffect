"""结果查询 - 查询测试结果和历史记录

职责：
- 查询单个用例结果
- 列出所有结果并汇总
- 查询历史执行记录
- 获取用例执行汇总
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from framework.core.history import HistoryManager
from framework.core.models import summarize_statuses
from framework.core.result_models import ListResultsResponse, dict_to_summary


class ResultQuery:
    """结果查询管理器"""

    def __init__(self, result_dir: str = "", history: HistoryManager | None = None) -> None:
        if not result_dir:
            from framework.core.config import get_config
            result_dir = get_config().result_dir
        self.result_dir = Path(result_dir)
        self.history = history or HistoryManager()

    def get_result(self, case_name: str) -> dict[str, Any] | None:
        """获取单个用例的最新结果"""
        f = self.result_dir / f"{case_name}.json"
        if not f.exists():
            return None
        result: dict[str, Any] = json.loads(f.read_text(encoding="utf-8"))
        return result

    def list_results(self) -> ListResultsResponse:
        """列出所有结果及汇总"""
        results: list[dict[str, Any]] = []
        if self.result_dir.exists():
            for f in sorted(self.result_dir.glob("*.json")):
                if f.name.startswith("report"):
                    continue
                try:
                    results.append(
                        json.loads(f.read_text(encoding="utf-8")),
                    )
                except json.JSONDecodeError:
                    pass
        summary_dict = summarize_statuses(results)
        return ListResultsResponse(
            summary=dict_to_summary(summary_dict),
            results=results,
        )

    def query_history(
        self, *, suite: str | None = None, environment: str | None = None,
        case_name: str | None = None, limit: int = 50,
    ) -> list[dict[str, Any]]:
        """查询执行历史"""
        return self.history.query(
            suite=suite, environment=environment,
            case_name=case_name, limit=limit,
        )

    def case_summary(self, case_name: str) -> dict[str, Any]:
        """获取单个用例的历史执行汇总"""
        return self.history.case_summary(case_name)
