"""结果服务 - 门面类（Facade Pattern）

职责：
- 统一对外接口，整合所有结果管理功能
- 保持向后兼容性
- 代理到各个子模块

重构说明：
- 原 464 行单体类拆分为 4 个模块
- 使用门面模式保持接口不变
- 降低复杂度，提高可维护性
"""

from __future__ import annotations

from typing import Any

from framework.core.history import HistoryManager
from framework.core.models import SuiteResult
from framework.core.result_models import CompareResponse, ListResultsResponse, UploadResult
from framework.services.result import (
    ResultCompare,
    ResultQuery,
    ResultStorage,
    ResultUploader,
    StorageConfig,
)


class ResultService:
    """统一结果管理 - 门面类

    整合 4 大能力:
      1. 结果存储: save, persist, clean
      2. 结果查询: get_result, list_results, query_history, case_summary
      3. 结果对比: compare_runs
      4. 结果上传: upload (API / rsync / local)
    """

    def __init__(
        self, result_dir: str = "", history_file: str = "",
        storage_config: StorageConfig | None = None,
    ) -> None:
        # 初始化共享的 history manager
        history = HistoryManager(history_file=history_file)

        # 初始化各个管理器
        self._storage = ResultStorage(result_dir=result_dir, history=history)
        self._query = ResultQuery(result_dir=result_dir, history=history)
        self._compare = ResultCompare(history=history)
        self._uploader = ResultUploader(
            result_dir=result_dir, query=self._query,
            storage_config=storage_config,
        )

        # 保留属性用于向后兼容
        self.result_dir = self._storage.result_dir
        self.history = history
        self.storage_config = self._uploader.storage_config

    # =====================================================================
    # 1. 结果存储（代理到 ResultStorage）
    # =====================================================================

    def save(self, suite_result: SuiteResult, **context: Any) -> str:
        """保存一次执行结果（持久化 + 历史记录），返回 run_id"""
        return self._storage.save(suite_result, **context)

    def clean_results(self) -> int:
        """清理结果目录下的所有 JSON 文件"""
        return self._storage.clean_results()

    # =====================================================================
    # 2. 结果查询（代理到 ResultQuery）
    # =====================================================================

    def get_result(self, case_name: str) -> dict[str, Any] | None:
        """获取单个用例的最新结果"""
        return self._query.get_result(case_name)

    def list_results(self) -> ListResultsResponse:
        """列出所有结果及汇总"""
        return self._query.list_results()

    def query_history(
        self, *, suite: str | None = None, environment: str | None = None,
        case_name: str | None = None, limit: int = 50,
    ) -> list[dict[str, Any]]:
        """查询执行历史"""
        return self._query.query_history(
            suite=suite, environment=environment,
            case_name=case_name, limit=limit,
        )

    def case_summary(self, case_name: str) -> dict[str, Any]:
        """获取单个用例的历史执行汇总"""
        return self._query.case_summary(case_name)

    # =====================================================================
    # 3. 结果对比（代理到 ResultCompare）
    # =====================================================================

    def compare_runs(self, run_id_a: str, run_id_b: str) -> CompareResponse:
        """对比两次执行结果"""
        return self._compare.compare_runs(run_id_a, run_id_b)

    # =====================================================================
    # 4. 结果导出
    # =====================================================================

    def export(self, fmt: str = "html") -> str:
        """生成报告，返回报告文件路径"""
        from framework.core.reporter import generate_report
        return generate_report(result_dir=str(self.result_dir), fmt=fmt)

    # =====================================================================
    # 5. 结果上传（代理到 ResultUploader）
    # =====================================================================

    def upload(
        self, *,
        config: StorageConfig | None = None,
        run_id: str = "",
    ) -> UploadResult:
        """上传结果到远端存储"""
        return self._uploader.upload(config=config, run_id=run_id)
