#!/usr/bin/env python3
"""回归测试入口脚本

用法:
    python scripts/run_regression.py [--suite default] [--parallel 4] [--config configs/default.yml]
"""

from __future__ import annotations

import argparse
import sys

from framework.core.collector import Collector
from framework.core.runner import TestRunner
from framework.utils.logger import setup_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="运行回归测试套件")
    parser.add_argument("--suite", default="default", help="套件名称")
    parser.add_argument("--parallel", "-p", type=int, default=1, help="并行任务数")
    parser.add_argument("--config", "-c", default="configs/default.yml", help="配置文件")
    args = parser.parse_args()

    setup_logging(level="INFO")

    runner = TestRunner(config_path=args.config, parallel=args.parallel)
    result = runner.run_suite(args.suite)

    # 持久化结果
    collector = Collector(output_dir="results")
    collector.save_results(result.results)

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
