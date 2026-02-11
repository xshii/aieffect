"""结果服务 — 统一结果存储 / 查询 / 对比 / 导出

将 collector + history + reporter 整合为统一的结果管理 API，
提供结果生命周期管理。
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

from framework.core.history import HistoryManager
from framework.core.models import SuiteResult, summarize_statuses

logger = logging.getLogger(__name__)


class ResultService:
    """统一结果管理"""

    def __init__(self, result_dir: str = "", history_file: str = "") -> None:
        if not result_dir:
            from framework.core.config import get_config
            result_dir = get_config().result_dir
        self.result_dir = Path(result_dir)
        self.result_dir.mkdir(parents=True, exist_ok=True)
        self.history = HistoryManager(history_file=history_file)

    # ---- 保存 ----

    def save(self, suite_result: SuiteResult, **context: Any) -> str:
        """保存一次执行结果（持久化 + 历史记录），返回 run_id"""
        # 1. 持久化每个用例结果为 JSON
        for r in suite_result.results:
            f = self.result_dir / f"{r.name}.json"
            f.write_text(json.dumps(asdict(r), indent=2, ensure_ascii=False), encoding="utf-8")

        # 2. 记录到历史
        entry = self.history.record_run(
            suite=context.get("suite", suite_result.suite_name),
            results=[asdict(r) for r in suite_result.results],
            environment=context.get("environment", suite_result.environment),
            snapshot_id=context.get("snapshot_id", suite_result.snapshot_id),
            params=context.get("params"),
        )
        logger.info("结果已保存: run_id=%s, %d 条", entry["run_id"], len(suite_result.results))
        return str(entry["run_id"])

    # ---- 查询 ----

    def get_result(self, case_name: str) -> dict[str, Any] | None:
        """获取单个用例的最新结果"""
        f = self.result_dir / f"{case_name}.json"
        if not f.exists():
            return None
        result: dict[str, Any] = json.loads(f.read_text(encoding="utf-8"))
        return result

    def list_results(self) -> dict[str, Any]:
        """列出所有结果及汇总"""
        results: list[dict[str, Any]] = []
        if self.result_dir.exists():
            for f in sorted(self.result_dir.glob("*.json")):
                if f.name.startswith("report"):
                    continue
                try:
                    results.append(json.loads(f.read_text(encoding="utf-8")))
                except json.JSONDecodeError:
                    pass
        return {
            "summary": summarize_statuses(results),
            "results": results,
        }

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

    # ---- 对比 ----

    def compare_runs(self, run_id_a: str, run_id_b: str) -> dict[str, Any]:
        """对比两次执行结果"""
        all_records = self.history.query(limit=10000)
        rec_a = next((r for r in all_records if r.get("run_id") == run_id_a), None)
        rec_b = next((r for r in all_records if r.get("run_id") == run_id_b), None)

        if rec_a is None or rec_b is None:
            missing = []
            if rec_a is None:
                missing.append(run_id_a)
            if rec_b is None:
                missing.append(run_id_b)
            return {"error": f"未找到记录: {', '.join(missing)}"}

        cases_a = {r["name"]: r for r in rec_a.get("results", [])}
        cases_b = {r["name"]: r for r in rec_b.get("results", [])}
        all_names = sorted(set(cases_a) | set(cases_b))

        diffs: list[dict[str, str]] = []
        for name in all_names:
            a_status = cases_a.get(name, {}).get("status", "—")
            b_status = cases_b.get(name, {}).get("status", "—")
            if a_status != b_status:
                diffs.append({"case": name, run_id_a: a_status, run_id_b: b_status})

        return {
            "run_a": {"run_id": run_id_a, "summary": rec_a.get("summary", {})},
            "run_b": {"run_id": run_id_b, "summary": rec_b.get("summary", {})},
            "diffs": diffs,
            "total_cases": len(all_names),
            "changed_cases": len(diffs),
        }

    # ---- 导出 ----

    def export(self, fmt: str = "html") -> str:
        """生成报告，返回报告文件路径"""
        from framework.core.reporter import generate_report
        return generate_report(result_dir=str(self.result_dir), fmt=fmt)

    # ---- 清理 ----

    def clean_results(self) -> int:
        """清理结果目录下的所有 JSON 文件"""
        count = 0
        for f in self.result_dir.glob("*.json"):
            f.unlink()
            count += 1
        logger.info("已清理 %d 个结果文件", count)
        return count
