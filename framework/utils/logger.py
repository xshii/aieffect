"""aieffect 日志配置"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """结构化 JSON 日志格式器，便于 CI 流水线消费"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def setup_logging(level: str = "INFO", json_output: bool = False) -> None:
    """配置根日志器

    参数:
        level: 日志级别字符串（DEBUG, INFO, WARNING, ERROR）
        json_output: 为 True 时使用 JSON 格式（适用于 CI），否则使用人类可读格式
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    handler = logging.StreamHandler(sys.stderr)

    if json_output:
        handler.setFormatter(JSONFormatter())
    else:
        fmt = "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s"
        handler.setFormatter(logging.Formatter(fmt))

    root.addHandler(handler)
