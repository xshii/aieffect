"""StimulusService 单元测试"""

from __future__ import annotations

import pytest

from framework.core.exceptions import CaseNotFoundError, ValidationError
from framework.core.models import ResultStimulusSpec, StimulusSpec, TriggerSpec


class TestStimulusService:
    """激励服务测试"""

    @pytest.fixture()
    def svc(self, tmp_path):
        from framework.services.stimulus_service import StimulusService
        return StimulusService(
            registry_file=str(tmp_path / "stimuli.yml"),
            artifact_dir=str(tmp_path / "artifacts"),
        )

    # ---- 激励管理 CRUD ----

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

    # ---- 激励构造 ----

    def test_construct_from_template(self, svc, tmp_path):
        tmpl = tmp_path / "stim_tmpl.txt"
        tmpl.write_text("seed=${seed} count=${count}", encoding="utf-8")
        svc.register(StimulusSpec(
            name="tmpl_stim", source_type="generated",
            template=str(tmpl),
            params={"seed": "42", "count": "100"},
        ))
        art = svc.construct("tmpl_stim", params={"seed": "99"})
        assert art.status == "ready"
        content = (tmp_path / "artifacts" / "tmpl_stim_constructed" /
                   "tmpl_stim_stimulus.txt").read_text(encoding="utf-8")
        assert "seed=99" in content
        assert "count=100" in content  # 默认参数保留

    def test_construct_inline_template(self, svc):
        svc.register(StimulusSpec(
            name="inline", source_type="generated",
            template="value=$(val)",
            params={"val": "default"},
        ))
        art = svc.construct("inline", params={"val": "override"})
        assert art.status == "ready"

    def test_construct_with_cmd(self, svc, tmp_path):
        svc.register(StimulusSpec(
            name="cmd_stim", source_type="generated",
            generator_cmd="echo $STIM_MSG > out.txt",
            params={"msg": "hello"},
        ))
        art = svc.construct("cmd_stim")
        assert art.status == "ready"

    def test_construct_nonexistent_raises(self, svc):
        with pytest.raises(CaseNotFoundError, match="不存在"):
            svc.construct("no_such")

    def test_construct_no_template_or_cmd_raises(self, svc):
        svc.register(StimulusSpec(name="empty", source_type="generated"))
        with pytest.raises(ValidationError, match="template"):
            svc.construct("empty")

    # ---- 结果激励管理 ----

    def test_register_result_stimulus_binary(self, svc, tmp_path):
        binfile = tmp_path / "result.bin"
        binfile.write_bytes(b"\x00\x01\x02")
        spec = ResultStimulusSpec(
            name="bin_result", source_type="binary",
            binary_path=str(binfile), description="二进制结果",
        )
        entry = svc.register_result_stimulus(spec)
        assert entry["source_type"] == "binary"

    def test_register_result_stimulus_empty_name_raises(self, svc):
        with pytest.raises(ValidationError, match="name"):
            svc.register_result_stimulus(ResultStimulusSpec(name=""))

    def test_register_result_stimulus_invalid_type_raises(self, svc):
        with pytest.raises(ValidationError, match="不支持"):
            svc.register_result_stimulus(ResultStimulusSpec(name="x", source_type="ftp"))

    def test_list_result_stimuli(self, svc):
        svc.register_result_stimulus(ResultStimulusSpec(name="a", source_type="api"))
        svc.register_result_stimulus(ResultStimulusSpec(name="b", source_type="binary"))
        assert len(svc.list_result_stimuli()) == 2

    def test_remove_result_stimulus(self, svc):
        svc.register_result_stimulus(ResultStimulusSpec(name="tmp"))
        assert svc.remove_result_stimulus("tmp") is True
        assert svc.remove_result_stimulus("tmp") is False

    def test_collect_result_binary(self, svc, tmp_path):
        binfile = tmp_path / "data.bin"
        binfile.write_bytes(b"data_content")
        svc.register_result_stimulus(ResultStimulusSpec(
            name="collect_test", source_type="binary",
            binary_path=str(binfile),
        ))
        art = svc.collect_result_stimulus("collect_test")
        assert art.status == "ready"
        assert art.local_path != ""

    def test_collect_result_nonexistent_raises(self, svc):
        with pytest.raises(CaseNotFoundError, match="不存在"):
            svc.collect_result_stimulus("no_such")

    # ---- 激励触发 ----

    def test_register_trigger_binary(self, svc):
        spec = TriggerSpec(
            name="bin_trigger", trigger_type="binary",
            binary_cmd="echo trigger", stimulus_name="gen_test",
        )
        entry = svc.register_trigger(spec)
        assert entry["trigger_type"] == "binary"

    def test_register_trigger_empty_name_raises(self, svc):
        with pytest.raises(ValidationError, match="name"):
            svc.register_trigger(TriggerSpec(name=""))

    def test_register_trigger_invalid_type_raises(self, svc):
        with pytest.raises(ValidationError, match="不支持"):
            svc.register_trigger(TriggerSpec(name="x", trigger_type="ftp"))

    def test_list_triggers(self, svc):
        svc.register_trigger(TriggerSpec(name="a", binary_cmd="echo a"))
        svc.register_trigger(TriggerSpec(name="b", binary_cmd="echo b"))
        assert len(svc.list_triggers()) == 2

    def test_remove_trigger(self, svc):
        svc.register_trigger(TriggerSpec(name="tmp", binary_cmd="echo"))
        assert svc.remove_trigger("tmp") is True
        assert svc.remove_trigger("tmp") is False

    def test_trigger_binary(self, svc, tmp_path):
        stim_file = tmp_path / "stim.txt"
        stim_file.write_text("test_stimulus", encoding="utf-8")
        svc.register_trigger(TriggerSpec(
            name="fire_test", trigger_type="binary",
            binary_cmd="echo fired",
        ))
        result = svc.trigger("fire_test", stimulus_path=str(stim_file))
        assert result.status == "success"

    def test_trigger_nonexistent_raises(self, svc):
        with pytest.raises(CaseNotFoundError, match="不存在"):
            svc.trigger("no_such")
