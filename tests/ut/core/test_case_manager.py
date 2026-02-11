"""用例表单管理器测试"""

from pathlib import Path

from framework.core.case_manager import CaseManager


class TestCaseManager:
    def test_add_and_list(self, tmp_path: Path) -> None:
        cm = CaseManager(cases_file=str(tmp_path / "cases.yml"))
        cm.add_case("tc1", "echo hello", description="测试1", tags=["smoke"], environments=["sim"])
        cm.add_case("tc2", "echo world", tags=["full"])

        cases = cm.list_cases()
        assert len(cases) == 2
        assert cases[0]["name"] == "tc1"
        assert cases[0]["environments"] == ["sim"]

    def test_filter_by_tag(self, tmp_path: Path) -> None:
        cm = CaseManager(cases_file=str(tmp_path / "cases.yml"))
        cm.add_case("a", "cmd_a", tags=["smoke"])
        cm.add_case("b", "cmd_b", tags=["full"])

        smoke = cm.list_cases(tag="smoke")
        assert len(smoke) == 1
        assert smoke[0]["name"] == "a"

    def test_filter_by_env(self, tmp_path: Path) -> None:
        cm = CaseManager(cases_file=str(tmp_path / "cases.yml"))
        cm.add_case("a", "cmd_a", environments=["sim"])
        cm.add_case("b", "cmd_b", environments=["fpga"])

        sim = cm.list_cases(environment="sim")
        assert len(sim) == 1
        assert sim[0]["name"] == "a"

    def test_get_and_remove(self, tmp_path: Path) -> None:
        cm = CaseManager(cases_file=str(tmp_path / "cases.yml"))
        cm.add_case("tc1", "echo 1")

        case = cm.get_case("tc1")
        assert case is not None
        assert case["cmd"] == "echo 1"

        assert cm.remove_case("tc1") is True
        assert cm.get_case("tc1") is None
        assert cm.remove_case("nonexist") is False

    def test_update_case(self, tmp_path: Path) -> None:
        cm = CaseManager(cases_file=str(tmp_path / "cases.yml"))
        cm.add_case("tc1", "echo old")
        updated = cm.update_case("tc1", cmd="echo new", timeout=120)
        assert updated is not None
        assert updated["cmd"] == "echo new"
        assert updated["timeout"] == 120

    def test_validate_params(self, tmp_path: Path) -> None:
        cm = CaseManager(cases_file=str(tmp_path / "cases.yml"))
        cm.add_case("tc1", "run {mode}", params_schema={
            "mode": {"type": "choice", "choices": ["fast", "full"]},
            "seed": {"type": "string", "default": "0"},
        })

        errors = cm.validate_params("tc1", {"mode": "fast"})
        assert errors == []

        errors = cm.validate_params("tc1", {"mode": "invalid"})
        assert len(errors) == 1

        errors = cm.validate_params("tc1", {})
        assert len(errors) == 1  # mode 缺失，seed 有默认值

    def test_environment_crud(self, tmp_path: Path) -> None:
        cm = CaseManager(cases_file=str(tmp_path / "cases.yml"))
        cm.add_environment("sim", description="仿真环境", variables={"TOOL": "vcs"})

        envs = cm.list_environments()
        assert len(envs) == 1
        assert envs[0]["name"] == "sim"

        assert cm.remove_environment("sim") is True
        assert cm.list_environments() == []

    def test_persistence(self, tmp_path: Path) -> None:
        path = str(tmp_path / "cases.yml")
        cm1 = CaseManager(cases_file=path)
        cm1.add_case("tc1", "echo persist")

        cm2 = CaseManager(cases_file=path)
        assert cm2.get_case("tc1") is not None
