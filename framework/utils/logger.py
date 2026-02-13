"""aieffect 日志配置

提供统一的日志配置和格式化功能，支持普通文本和结构化 JSON 两种输出格式。
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """结构化 JSON 日志格式器，便于 CI 流水线消费

    输出格式:
        {
            "timestamp": "2024-01-01T12:00:00+00:00",
            "level": "INFO",
            "logger": "module.name",
            "message": "log message",
            "module": "filename",
            "function": "func_name",
            "line": 42,
            "exception": "traceback..." (仅在有异常时)
        }
    """

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录为 JSON 字符串

        参数:
            record: 日志记录对象

        返回:
            str: JSON 格式的日志字符串
        """
        log_entry = {
            # 使用 record.created 而非 datetime.now()，记录事件发生时间而非格式化时间
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            # 添加更多上下文信息，便于调试
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def setup_logging(level: str = "INFO", json_output: bool = False) -> None:
    """配置根日志器

    参数:
        level: 日志级别字符串（DEBUG, INFO, WARNING, ERROR, CRITICAL）
        json_output: 为 True 时使用 JSON 格式（适用于 CI），否则使用人类可读格式

    说明:
        - 输出到 stderr
        - 自动清理已有 handlers，避免重复输出
        - JSON 格式包含详细上下文（模块、函数、行号）
        - 普通格式为人类可读的时间戳+级别+消息

    示例:
        >>> setup_logging("DEBUG", json_output=False)
        >>> setup_logging("INFO", json_output=True)  # CI 环境
    """
    root = logging.getLogger()

    # 清理已有 handlers，避免重复添加导致日志重复输出
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()

    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    handler = logging.StreamHandler(sys.stderr)

    if json_output:
        handler.setFormatter(JSONFormatter())
    else:
        fmt = "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s"
        handler.setFormatter(logging.Formatter(fmt))

    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的 logger 实例

    参数:
        name: logger 名称，通常使用 __name__

    返回:
        logging.Logger: logger 实例

    示例:
        >>> logger = get_logger(__name__)
        >>> logger.info("Starting process...")
    """
    return logging.getLogger(name)


def reset_logging() -> None:
    """重置根日志器配置

    清理所有已注册的 handlers，恢复到未配置状态。
    常用于测试环境或需要重新配置日志的场景。

    示例:
        >>> reset_logging()
        >>> setup_logging("DEBUG")  # 重新配置
    """
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
