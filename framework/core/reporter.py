"""测试报告生成器 - Strategy 模式

每种报告格式实现 ResultFormatter 接口，通过注册制工厂调用。
新增格式只需继承 ResultFormatter 并注册即可。
"""

from __future__ import annotations

import html
import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from xml.sax.saxutils import quoteattr as xml_quoteattr

from framework.core.models import summarize_statuses

logger = logging.getLogger(__name__)


def _load_results(result_dir: str) -> list[dict]:
    result_path = Path(result_dir)
    if not result_path.exists():
        return []
    results = []
    for json_file in sorted(result_path.glob("*.json")):
        if json_file.name.startswith("report"):
            continue
        with open(json_file, encoding="utf-8") as file_handle:
            results.append(json.load(file_handle))
    return results


# =========================================================================
# Strategy: ResultFormatter
# =========================================================================


class ResultFormatter(ABC):
    """报告格式化策略基类"""

    @abstractmethod
    def format(self, results: list[dict], summary: dict) -> str:
        """将结果列表格式化为字符串"""

    @abstractmethod
    def extension(self) -> str:
        """输出文件扩展名（不含 .）"""


class JSONFormatter(ResultFormatter):
    def format(self, results: list[dict], summary: dict) -> str:
        return json.dumps(
            {"summary": summary, "details": results}, indent=2,
        )

    def extension(self) -> str:
        return "json"


class HTMLFormatter(ResultFormatter):
    def format(self, results: list[dict], summary: dict) -> str:
        rows = ""
        for case_data in results:
            status = case_data.get("status", "unknown")
            css = {"passed": "pass", "failed": "fail", "error": "error"}.get(status, "")
            name = html.escape(str(case_data.get("name", "")))
            msg = html.escape(str(case_data.get("message", "")))
            rows += (
                f'<tr class="{css}">'
                f"<td>{name}</td>"
                f"<td>{html.escape(status)}</td>"
                f'<td>{case_data.get("duration", 0):.1f}s</td>'
                f"<td>{msg}</td>"
                f"</tr>\n"
            )

        return (
            "<!DOCTYPE html>\n"
            '<html><head><meta charset="utf-8">'
            "<title>aieffect 测试报告</title>\n<style>\n"
            "  body { font-family: monospace; margin: 2em; }\n"
            "  table { border-collapse: collapse; width: 100%; }\n"
            "  th, td { border: 1px solid #ccc; padding: 6px 12px;"
            " text-align: left; }\n"
            "  .pass { background: #d4edda; }\n"
            "  .fail { background: #f8d7da; }\n"
            "  .error { background: #fff3cd; }\n"
            "</style></head><body>\n"
            "<h1>aieffect 测试报告</h1>\n"
            f"<p>总计: {summary['total']} | 通过: {summary['passed']}"
            f" | 失败: {summary['failed']} | 错误: {summary['errors']}</p>\n"
            "<table>\n"
            "<tr><th>用例名</th><th>状态</th><th>耗时</th>"
            "<th>信息</th></tr>\n"
            f"{rows}"
            "</table></body></html>"
        )

    def extension(self) -> str:
        return "html"


class JUnitFormatter(ResultFormatter):
    def format(self, results: list[dict], summary: dict) -> str:
        testcases = ""
        for case_data in results:
            name_attr = xml_quoteattr(str(case_data.get("name", "unknown")))
            duration = case_data.get("duration", 0)
            status = case_data.get("status", "unknown")
            msg_attr = xml_quoteattr(str(case_data.get("message", "")))

            if status == "passed":
                testcases += f'    <testcase name={name_attr} time="{duration:.1f}"/>\n'
            elif status == "failed":
                testcases += (
                    f'    <testcase name={name_attr} time="{duration:.1f}">\n'
                    f"      <failure message={msg_attr}/>\n"
                    f"    </testcase>\n"
                )
            else:
                testcases += (
                    f'    <testcase name={name_attr} time="{duration:.1f}">\n'
                    f"      <error message={msg_attr}/>\n"
                    f"    </testcase>\n"
                )

        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<testsuite name="aieffect" tests="{summary["total"]}" '
            f'failures="{summary["failed"]}" errors="{summary["errors"]}">\n'
            f"{testcases}"
            "</testsuite>\n"
        )

    def extension(self) -> str:
        return "xml"


# =========================================================================
# 注册制工厂
# =========================================================================

_formatters: dict[str, type[ResultFormatter]] = {
    "html": HTMLFormatter,
    "json": JSONFormatter,
    "junit": JUnitFormatter,
}


def register_formatter(name: str, cls: type[ResultFormatter]) -> None:
    """注册自定义报告格式"""
    _formatters[name] = cls


def generate_report(result_dir: str = "results", fmt: str = "html") -> str:
    """从结果 JSON 文件生成报告，返回生成的文件路径"""
    results = _load_results(result_dir)
    if not results:
        logger.warning("在 %s 中未找到结果文件", result_dir)
        return ""

    formatter_cls = _formatters.get(fmt)
    if formatter_cls is None:
        raise ValueError(
            f"不支持的格式: {fmt}（可用: {list(_formatters)}）",
        )

    formatter = formatter_cls()
    summary = summarize_statuses(results)
    content = formatter.format(results, summary)

    output = Path(result_dir) / f"report.{formatter.extension()}"
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info("报告已生成: %s", output)
    return str(output)
