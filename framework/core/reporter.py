"""测试报告生成器 - 支持 HTML / JSON / JUnit XML"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _summarize(results: list[dict]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r.get("status") == "passed")
    failed = sum(1 for r in results if r.get("status") == "failed")
    errors = sum(1 for r in results if r.get("status") == "error")
    return {"total": total, "passed": passed, "failed": failed, "errors": errors}


def _load_results(result_dir: str) -> list[dict]:
    rdir = Path(result_dir)
    if not rdir.exists():
        return []
    results = []
    for f in sorted(rdir.glob("*.json")):
        if f.name.startswith("report"):
            continue
        with open(f) as fh:
            results.append(json.load(fh))
    return results


def generate_report(result_dir: str = "results", fmt: str = "html") -> str:
    """从结果 JSON 文件生成报告，返回生成的文件路径"""
    results = _load_results(result_dir)
    if not results:
        logger.warning("在 %s 中未找到结果文件", result_dir)
        return ""

    generators = {"html": _gen_html, "json": _gen_json, "junit": _gen_junit}
    generator = generators.get(fmt)
    if not generator:
        raise ValueError(f"不支持的格式: {fmt}")

    output_path = generator(results, result_dir)
    logger.info("报告已生成: %s", output_path)
    return output_path


def _gen_json(results: list[dict], result_dir: str) -> str:
    output = Path(result_dir) / "report.json"
    summary = _summarize(results)
    with open(output, "w") as f:
        json.dump({"summary": summary, "details": results}, f, indent=2)
    return str(output)


def _gen_html(results: list[dict], result_dir: str) -> str:
    output = Path(result_dir) / "report.html"
    summary = _summarize(results)

    rows = ""
    for r in results:
        status = r.get("status", "unknown")
        css_class = {"passed": "pass", "failed": "fail", "error": "error"}.get(status, "")
        rows += (
            f'<tr class="{css_class}">'
            f'<td>{r.get("name", "")}</td>'
            f"<td>{status}</td>"
            f'<td>{r.get("duration", 0):.1f}s</td>'
            f'<td>{r.get("message", "")}</td>'
            f"</tr>\n"
        )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>aieffect 测试报告</title>
<style>
  body {{ font-family: monospace; margin: 2em; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 12px; text-align: left; }}
  .pass {{ background: #d4edda; }}
  .fail {{ background: #f8d7da; }}
  .error {{ background: #fff3cd; }}
</style></head><body>
<h1>aieffect 测试报告</h1>
<p>总计: {summary['total']} | 通过: {summary['passed']} | 失败: {summary['failed']} | 错误: {summary['errors']}</p>
<table>
<tr><th>用例名</th><th>状态</th><th>耗时</th><th>信息</th></tr>
{rows}
</table></body></html>"""

    with open(output, "w") as f:
        f.write(html)
    return str(output)


def _gen_junit(results: list[dict], result_dir: str) -> str:
    output = Path(result_dir) / "report.xml"
    summary = _summarize(results)

    testcases = ""
    for r in results:
        name = r.get("name", "unknown")
        duration = r.get("duration", 0)
        status = r.get("status", "unknown")
        msg = r.get("message", "")

        if status == "passed":
            testcases += f'    <testcase name="{name}" time="{duration:.1f}"/>\n'
        elif status == "failed":
            testcases += (
                f'    <testcase name="{name}" time="{duration:.1f}">\n'
                f'      <failure message="{msg}"/>\n'
                f"    </testcase>\n"
            )
        else:
            testcases += (
                f'    <testcase name="{name}" time="{duration:.1f}">\n'
                f'      <error message="{msg}"/>\n'
                f"    </testcase>\n"
            )

    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<testsuite name="aieffect" tests="{summary["total"]}" '
        f'failures="{summary["failed"]}" errors="{summary["errors"]}">\n'
        f"{testcases}"
        f"</testsuite>\n"
    )

    with open(output, "w") as f:
        f.write(xml)
    return str(output)
