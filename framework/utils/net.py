"""网络工具 — URL 安全校验"""

from __future__ import annotations

from urllib.parse import urlparse

from framework.core.exceptions import ValidationError

_ALLOWED_SCHEMES = frozenset(("http", "https"))


def validate_url_scheme(url: str, *, context: str = "") -> None:
    """校验 URL 仅使用 http/https，防止 file:// 等非预期协议访问

    Raises:
        ValidationError: URL scheme 不在白名单内
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        label = f" ({context})" if context else ""
        raise ValidationError(
            f"不允许的 URL 协议 '{parsed.scheme}'{label}，"
            f"仅支持 http/https: {url}"
        )
