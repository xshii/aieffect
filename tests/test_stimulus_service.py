"""StimulusService 单元测试"""

from __future__ import annotations

import pytest

from framework.core.exceptions import CaseNotFoundError, ValidationError
from framework.core.models import StimulusSpec


class TestStimulusService:
    """激励服务测试"""

    @pytest.fixture()
    def svc(self, tmp_path):
        from framework.services.stimulus_service import StimulusService
        return StimulusService(
            registry_file=str(tmp_path / "stimuli.yml"),
            artifact_dir=str(tmp_path / "artifacts"),
        )

    def test_register_generated(self, svc):
        spec = StimulusSpec(
            name="rand_vectors", source_type="generated",
            generator_cmd="python gen.py", description="随机激励",
        )
        entry = svc.register(spec)
        assert entry["source_type"] == "generated"
        assert entry["generator_cmd"] == "python gen.py"

    def test_register_stored(self, svc):
        spec = StimulusSpec(name="golden", source_type="stored", storage_key="golden_v1")
        entry = svc.register(spec)
        assert entry["storage_key"] == "golden_v1"

    def test_register_external(self, svc):
        spec = StimulusSpec(
            name="ext", source_type="external",
            external_url="https://data.example.com/vectors.tar.gz",
        )
        entry = svc.register(spec)
        assert entry["external_url"].startswith("https://")

    def test_register_empty_name_raises(self, svc):
        with pytest.raises(ValidationError, match="name"):
            svc.register(StimulusSpec(name=""))

    def test_register_invalid_type(self, svc):
        with pytest.raises(ValidationError, match="不支持"):
            svc.register(StimulusSpec(name="x", source_type="ftp"))

    def test_get_and_list(self, svc):
        svc.register(StimulusSpec(name="a", source_type="generated", generator_cmd="echo a"))
        svc.register(StimulusSpec(name="b", source_type="stored", storage_key="b"))

        got = svc.get("a")
        assert got is not None
        assert got.source_type == "generated"
        assert len(svc.list_all()) == 2

    def test_remove(self, svc):
        svc.register(StimulusSpec(name="tmp", source_type="generated", generator_cmd="echo"))
        assert svc.remove("tmp") is True
        assert svc.remove("tmp") is False

    def test_acquire_nonexistent_raises(self, svc):
        with pytest.raises(CaseNotFoundError, match="不存在"):
            svc.acquire("no_such")

    def test_acquire_generated(self, svc, tmp_path):
        svc.register(StimulusSpec(
            name="gen_test", source_type="generated",
            generator_cmd="echo hello > output.txt",
        ))
        art = svc.acquire("gen_test")
        assert art.status == "ready"
        assert art.local_path != ""

    def test_acquire_generated_failure(self, svc):
        svc.register(StimulusSpec(
            name="bad_gen", source_type="generated",
            generator_cmd="false",  # exit code 1
        ))
        art = svc.acquire("bad_gen")
        assert art.status == "error"
