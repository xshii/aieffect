"""结果存储 - 持久化测试结果

职责：
- 将测试结果持久化到文件系统
- 记录到历史管理器
- 收集上下文元信息
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

from framework.core.history import HistoryManager
from framework.core.models import SuiteResult

logger = logging.getLogger(__name__)


class ResultStorage:
    """结果存储管理器"""

    def __init__(self, result_dir: str = "", history: HistoryManager | None = None) -> None:
        if not result_dir:
            from framework.core.config import get_config
            result_dir = get_config().result_dir
        self.result_dir = Path(result_dir)
        self.result_dir.mkdir(parents=True, exist_ok=True)
        self.history = history or HistoryManager()

    def save(self, suite_result: SuiteResult, **context: Any) -> str:
        """保存一次执行结果（持久化 + 历史记录），返回 run_id

        结果包含测试元信息和结果数据路径配置。
        """
        self._persist_results(suite_result)
        meta = self._collect_context_dict(
            context,
            ("repo_name", "repo_ref", "repo_commit",
             "build_env", "exe_env", "stimulus_name"),
            extra_key="extra_meta",
        )
        result_paths = self._collect_context_dict(
            context,
            ("log_path", "waveform_path", "coverage_path",
             "report_path", "artifact_dir"),
            extra_key="custom_paths",
        )
        entry = self.history.record_run(
            suite=context.get("suite", suite_result.suite_name),
            results=[asdict(r) for r in suite_result.results],
            environment=context.get("environment", suite_result.environment),
            snapshot_id=context.get(
                "snapshot_id", suite_result.snapshot_id,
            ),
            params=context.get("params"),
            meta=meta or None,
            result_paths=result_paths or None,
        )
        logger.info(
            "结果已保存: run_id=%s, %d 条",
            entry["run_id"], len(suite_result.results),
        )
        return str(entry["run_id"])

    def _persist_results(self, suite_result: SuiteResult) -> None:
        """将结果持久化到文件系统"""
        for r in suite_result.results:
            f = self.result_dir / f"{r.name}.json"
            f.write_text(
                json.dumps(asdict(r), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    @staticmethod
    def _collect_context_dict(
        context: dict[str, Any], keys: tuple[str, ...],
        *, extra_key: str = "",
    ) -> dict[str, Any]:
        """从上下文中收集指定字段"""
        result: dict[str, Any] = {}
        for key in keys:
            val = context.get(key, "")
            if val:
                result[key] = val
        if extra_key and context.get(extra_key):
            result.update(context[extra_key])
        return result

    def clean_results(self) -> int:
        """清理结果目录下的所有 JSON 文件"""
        count = 0
        for f in self.result_dir.glob("*.json"):
            f.unlink()
            count += 1
        logger.info("已清理 %d 个结果文件", count)
        return count
