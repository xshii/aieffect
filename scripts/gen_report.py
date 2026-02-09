#!/usr/bin/env python3
"""报告生成入口脚本

用法:
    python scripts/gen_report.py [--result-dir results] [--format html]
"""

from __future__ import annotations

import argparse

from framework.core.reporter import Reporter
from framework.utils.logger import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="生成测试报告")
    parser.add_argument("--result-dir", default="results", help="结果 JSON 文件所在目录")
    parser.add_argument("--format", "-f", default="html", choices=["html", "json", "junit"])
    args = parser.parse_args()

    setup_logging(level="INFO")

    reporter = Reporter()
    output = reporter.generate(result_dir=args.result_dir, fmt=args.format)
    if output:
        print(f"报告: {output}")
    else:
        print("未找到结果文件。")


if __name__ == "__main__":
    main()
