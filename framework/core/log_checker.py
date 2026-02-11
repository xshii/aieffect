"""日志匹配检查器

支持对上传的日志文件按预定义规则进行模式匹配检查：
  - required: 日志中必须包含该模式（缺失则失败）
  - forbidden: 日志中不得包含该模式（出现则失败）

规则定义在 YAML 配置中，格式：
  rules:
    - name: "规则名"
      pattern: "正则表达式"
      type: required | forbidden
      description: "说明"
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from framework.utils.yaml_io import load_yaml

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    """单条规则的检查结果"""

    rule_name: str
    rule_type: str  # required / forbidden
    passed: bool
    matches: list[str] = field(default_factory=list)
    message: str = ""


@dataclass
class LogCheckReport:
    """日志检查报告"""

    log_source: str
    total_rules: int = 0
    passed_rules: int = 0
    failed_rules: int = 0
    details: list[CheckResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.failed_rules == 0


class LogChecker:
    """日志匹配检查器"""

    def __init__(self, rules_file: str = "") -> None:
        if not rules_file:
            from framework.core.config import get_config
            rules_file = get_config().log_rules_file
        self.rules: list[dict] = []
        self._load_rules(rules_file)

    def _load_rules(self, path: str) -> None:
        p = Path(path)
        if not p.exists():
            logger.warning("日志检查规则文件不存在: %s", path)
            return
        data = load_yaml(p)
        self.rules = data.get("rules", [])
        logger.info("已加载 %d 条日志检查规则", len(self.rules))

    def check_text(self, text: str, source: str = "") -> LogCheckReport:
        """对文本内容执行所有规则检查"""
        report = LogCheckReport(log_source=source, total_rules=len(self.rules))

        for rule in self.rules:
            name = rule.get("name", "unnamed")
            pattern = rule.get("pattern", "")
            rule_type = rule.get("type", "required")

            if not pattern:
                continue

            try:
                found = re.findall(pattern, text, re.MULTILINE)
            except re.error as e:
                logger.warning("跳过无效规则 '%s': 正则表达式错误 - %s", name, e)
                report.details.append(CheckResult(
                    rule_name=name, rule_type=rule_type, passed=True,
                    message=f"跳过: 正则表达式错误 - {e}",
                ))
                report.passed_rules += 1
                continue

            if rule_type == "required":
                passed = len(found) > 0
                msg = "匹配成功" if passed else "未找到必需的模式"
            elif rule_type == "forbidden":
                passed = len(found) == 0
                msg = "通过（未出现禁止模式）" if passed else f"发现禁止模式 ({len(found)} 处)"
            else:
                logger.warning("跳过未知规则类型 '%s': 规则 '%s'", rule_type, name)
                passed = False
                msg = f"未知规则类型: {rule_type}"

            result = CheckResult(
                rule_name=name,
                rule_type=rule_type,
                passed=passed,
                matches=found[:10],  # 最多保留 10 条匹配
                message=msg,
            )
            report.details.append(result)
            if passed:
                report.passed_rules += 1
            else:
                report.failed_rules += 1

        return report

    def check_file(self, file_path: str, source: str = "") -> LogCheckReport:
        """对日志文件执行规则检查"""
        p = Path(file_path)
        if not p.exists():
            detail = CheckResult(
                rule_name="file_check", rule_type="required",
                passed=False, message=f"文件不存在: {file_path}",
            )
            return LogCheckReport(
                log_source=source or file_path, total_rules=0,
                failed_rules=1, details=[detail],
            )

        text = p.read_text(encoding="utf-8", errors="replace")
        return self.check_text(text, source=source or file_path)
