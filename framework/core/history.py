"""历史执行汇总 - 用例执行结果的历史记录与聚合查询

每次执行完成后追加一条记录到历史存储，支持：
  - 按用例名、环境、时间范围查询
  - 聚合统计通过率/失败率
  - 为 Web 表格提供数据源
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class HistoryManager:
    """执行历史管理器"""

    def __init__(self, history_file: str = "") -> None:
        if not history_file:
            from framework.core.config import get_config
            history_file = get_config().history_file
        self.history_file = Path(history_file)
        self.history_file.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict]:
        """从历史文件加载所有执行记录"""
        if not self.history_file.exists():
            return []
        with open(self.history_file, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []

    def _save(self, records: list[dict]) -> None:
        """原子性保存执行记录到历史文件"""
        from framework.utils.yaml_io import atomic_write
        content = json.dumps(records, indent=2, ensure_ascii=False)
        atomic_write(self.history_file, content)

    def record_run(
        self,
        suite: str,
        results: list[dict],
        *,
        environment: str = "",
        snapshot_id: str = "",
        params: dict | None = None,
        meta: dict | None = None,
        result_paths: dict | None = None,
    ) -> dict:
        """记录一次执行结果到历史"""
        from framework.core.models import summarize_statuses

        entry: dict = {
            "run_id": str(uuid.uuid4())[:8],
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "suite": suite,
            "environment": environment,
            "snapshot_id": snapshot_id,
            "params": params or {},
            "summary": summarize_statuses(results),
            "results": results,
        }
        if meta:
            entry["meta"] = meta
        if result_paths:
            entry["result_paths"] = result_paths

        records = self._load()
        records.append(entry)
        self._save(records)
        logger.info("执行历史已记录: run_id=%s, suite=%s", entry["run_id"], suite)
        return entry

    @staticmethod
    def _filter_by_case(records: list[dict], case_name: str) -> list[dict]:
        """保留包含指定用例的记录，并只展示该用例的结果"""
        filtered = []
        for r in records:
            case_results = [c for c in r.get("results", []) if c.get("name") == case_name]
            if case_results:
                filtered.append({**r, "results": case_results})
        return filtered

    def query(
        self,
        *,
        case_name: str | None = None,
        suite: str | None = None,
        environment: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """查询历史记录，支持过滤"""
        records = self._load()

        if suite:
            records = [r for r in records if r.get("suite") == suite]
        if environment:
            records = [r for r in records if r.get("environment") == environment]
        if case_name:
            records = self._filter_by_case(records, case_name)

        # 按时间倒序，取最近 limit 条
        records.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return records[:limit]

    def case_summary(self, case_name: str) -> dict:
        """获取单个用例的历史执行汇总"""
        records = self._load()
        runs: list[dict] = []
        for r in records:
            for c in r.get("results", []):
                if c.get("name") == case_name:
                    runs.append({
                        "run_id": r.get("run_id", ""),
                        "timestamp": r.get("timestamp", ""),
                        "environment": r.get("environment", ""),
                        "status": c.get("status", ""),
                        "duration": c.get("duration", 0),
                        "message": c.get("message", ""),
                    })

        total = len(runs)
        passed = sum(1 for r in runs if r["status"] == "passed")
        failed = sum(1 for r in runs if r["status"] == "failed")
        errors = sum(1 for r in runs if r["status"] == "error")
        skipped = sum(1 for r in runs if r["status"] == "skipped")
        pass_rate = (passed / total * 100) if total > 0 else 0

        return {
            "case_name": case_name,
            "total_runs": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "pass_rate": round(pass_rate, 1),
            "recent": runs[-10:] if runs else [],
        }

    def submit_external(self, run_data: dict) -> dict:
        """接收外部（本地执行）提交的执行结果"""
        required = ["suite", "results"]
        for field in required:
            if field not in run_data:
                raise ValueError(f"缺少必填字段: {field}")

        return self.record_run(
            suite=run_data["suite"],
            results=run_data["results"],
            environment=run_data.get("environment", ""),
            snapshot_id=run_data.get("snapshot_id", ""),
            params=run_data.get("params"),
        )
