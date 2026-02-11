"""EnvService 单元测试"""

from __future__ import annotations

import pytest

from framework.core.exceptions import CaseNotFoundError, ValidationError
from framework.core.models import EnvironmentSpec, ToolSpec


class TestEnvService:
    """环境服务测试"""

    @pytest.fixture()
    def svc(self, tmp_path):
        from framework.services.env_service import EnvService
        return EnvService(registry_file=str(tmp_path / "envs.yml"))

    def test_register_and_get(self, svc):
        spec = EnvironmentSpec(
            name="sim_env",
            description="仿真环境",
            tools={"vcs": ToolSpec(name="vcs", version="2023.03", install_path="/eda/vcs")},
            variables={"WORK_DIR": "/tmp/sim"},
            licenses={"LM_LICENSE_FILE": "1234@license.example.com"},
        )
        svc.register(spec)

        got = svc.get("sim_env")
        assert got is not None
        assert got.name == "sim_env"
        assert "vcs" in got.tools
        assert got.tools["vcs"].version == "2023.03"
        assert got.licenses["LM_LICENSE_FILE"] == "1234@license.example.com"

    def test_register_empty_name_raises(self, svc):
        with pytest.raises(ValidationError, match="name"):
            svc.register(EnvironmentSpec(name=""))

    def test_list_all(self, svc):
        svc.register(EnvironmentSpec(name="env_a"))
        svc.register(EnvironmentSpec(name="env_b"))
        assert len(svc.list_all()) == 2

    def test_remove(self, svc):
        svc.register(EnvironmentSpec(name="tmp"))
        assert svc.remove("tmp") is True
        assert svc.remove("tmp") is False

    def test_provision(self, svc, tmp_path):
        spec = EnvironmentSpec(
            name="dev",
            tools={"vcs": ToolSpec(name="vcs", version="2023.03", install_path="/eda/vcs",
                                   env_vars={"VCS_HOME": "{install_path}"})},
            variables={"MY_VAR": "hello"},
            licenses={"LM_LICENSE_FILE": "5678@lic"},
        )
        svc.register(spec)

        session = svc.provision("dev", work_dir=str(tmp_path / "work"))
        assert session.status == "ready"
        assert session.resolved_vars["MY_VAR"] == "hello"
        assert session.resolved_vars["LM_LICENSE_FILE"] == "5678@lic"
        assert session.resolved_vars["VCS_HOME"] == "/eda/vcs"
        assert "/eda/vcs/bin" in session.resolved_vars.get("PATH", "")

    def test_provision_nonexistent_raises(self, svc):
        with pytest.raises(CaseNotFoundError, match="不存在"):
            svc.provision("no_such_env")

    def test_execute_in(self, svc, tmp_path):
        svc.register(EnvironmentSpec(name="test_env"))
        session = svc.provision("test_env", work_dir=str(tmp_path))
        result = svc.execute_in(session, "echo hello", timeout=10)
        assert result["success"] is True
        assert "hello" in result["stdout"]

    def test_execute_timeout(self, svc, tmp_path):
        svc.register(EnvironmentSpec(name="slow_env"))
        session = svc.provision("slow_env", work_dir=str(tmp_path))
        result = svc.execute_in(session, "sleep 10", timeout=1)
        assert result["success"] is False
        assert "超时" in result["stderr"]

    def test_teardown(self, svc, tmp_path):
        svc.register(EnvironmentSpec(name="teardown_env"))
        session = svc.provision("teardown_env", work_dir=str(tmp_path))
        assert session.status == "ready"
        svc.teardown(session)
        assert session.status == "torn_down"

    def test_execute_after_teardown_raises(self, svc, tmp_path):
        svc.register(EnvironmentSpec(name="td_env"))
        session = svc.provision("td_env", work_dir=str(tmp_path))
        svc.teardown(session)
        with pytest.raises(ValidationError, match="不可用"):
            svc.execute_in(session, "echo fail")
