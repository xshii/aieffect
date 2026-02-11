"""URL scheme 校验测试"""

import pytest

from framework.utils.net import validate_url_scheme


class TestValidateUrlScheme:
    def test_http_ok(self) -> None:
        validate_url_scheme("http://example.com/api")

    def test_https_ok(self) -> None:
        validate_url_scheme("https://example.com/api")

    def test_file_rejected(self) -> None:
        with pytest.raises(ValueError, match="不允许的 URL 协议"):
            validate_url_scheme("file:///etc/passwd")

    def test_ftp_rejected(self) -> None:
        with pytest.raises(ValueError, match="不允许的 URL 协议"):
            validate_url_scheme("ftp://evil.com/payload")

    def test_empty_scheme_rejected(self) -> None:
        with pytest.raises(ValueError, match="不允许的 URL 协议"):
            validate_url_scheme("/local/path")

    def test_context_in_error(self) -> None:
        with pytest.raises(ValueError, match="dep download"):
            validate_url_scheme("file:///x", context="dep download foo")
