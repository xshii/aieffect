"""YamlRegistry 基类单元测试"""

from __future__ import annotations

from pathlib import Path

import pytest

from framework.core.registry import YamlRegistry


class ConcreteRegistry(YamlRegistry):
    section_key = "items"


@pytest.fixture()
def registry(tmp_path: Path) -> ConcreteRegistry:
    reg_file = tmp_path / "reg.yml"
    reg_file.write_text("{}", encoding="utf-8")
    return ConcreteRegistry(str(reg_file))


class TestYamlRegistryCRUD:
    def test_put_and_get(self, registry: ConcreteRegistry) -> None:
        registry._put("foo", {"x": 1})
        assert registry._get_raw("foo") == {"x": 1}

    def test_get_missing_returns_none(self, registry: ConcreteRegistry) -> None:
        assert registry._get_raw("nonexistent") is None

    def test_list_raw_empty(self, registry: ConcreteRegistry) -> None:
        assert registry._list_raw() == []

    def test_list_raw_with_entries(self, registry: ConcreteRegistry) -> None:
        registry._put("a", {"v": 1})
        registry._put("b", {"v": 2})
        items = registry._list_raw()
        assert len(items) == 2
        names = {i["name"] for i in items}
        assert names == {"a", "b"}

    def test_remove_existing(self, registry: ConcreteRegistry) -> None:
        registry._put("x", {"val": 42})
        assert registry._remove("x") is True
        assert registry._get_raw("x") is None

    def test_remove_missing(self, registry: ConcreteRegistry) -> None:
        assert registry._remove("nonexistent") is False

    def test_put_overwrites(self, registry: ConcreteRegistry) -> None:
        registry._put("k", {"old": True})
        registry._put("k", {"new": True})
        assert registry._get_raw("k") == {"new": True}

    def test_persistence(self, tmp_path: Path) -> None:
        reg_file = tmp_path / "persist.yml"
        reg_file.write_text("{}", encoding="utf-8")
        r1 = ConcreteRegistry(str(reg_file))
        r1._put("persisted", {"a": 1})
        r2 = ConcreteRegistry(str(reg_file))
        assert r2._get_raw("persisted") == {"a": 1}

    def test_section_auto_created(self, tmp_path: Path) -> None:
        reg_file = tmp_path / "auto.yml"
        reg_file.write_text("{}", encoding="utf-8")
        reg = ConcreteRegistry(str(reg_file))
        section = reg._section()
        assert isinstance(section, dict)
        assert len(section) == 0
