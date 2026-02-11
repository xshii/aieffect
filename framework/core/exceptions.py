"""统一异常体系

所有业务异常继承 AIEffectError，替代散落的 ValueError / RuntimeError。
Web 层可据此自动映射 HTTP 状态码，CLI 层可据此输出友好提示。
"""

from __future__ import annotations


class AIEffectError(Exception):
    """框架基础异常"""

    code: str = "UNKNOWN"

    def __init__(self, message: str) -> None:
        super().__init__(message)


class ConfigError(AIEffectError):
    """配置文件缺失或内容无效"""

    code = "CONFIG_ERROR"


class CaseNotFoundError(AIEffectError):
    """指定的用例或套件不存在"""

    code = "CASE_NOT_FOUND"


class DependencyError(AIEffectError):
    """依赖包拉取或解析失败"""

    code = "DEPENDENCY_ERROR"


class ValidationError(AIEffectError):
    """输入数据校验失败"""

    code = "VALIDATION_ERROR"

    def __init__(self, message: str, details: list[str] | None = None) -> None:
        super().__init__(message)
        self.details = details or []
