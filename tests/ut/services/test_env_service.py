"""EnvService 单元测试（BuildEnv + ExeEnv 模型）"""

from __future__ import annotations

import pytest

from framework.core.exceptions import CaseNotFoundError, ValidationError
from framework.core.models import BuildEnvSpec, ExeEnvSpec, ToolSpec


class TestEnvService:
    """环境服务测试"""

    @pytest.fixture()
    def svc(self, tmp_path):
        from framework.services.env_service import EnvService
        return EnvService(registry_file=str(tmp_path / "envs.yml"))

    # ---- 构建环境 CRUD ----

    def test_register_build_env_local(self, svc):
        spec = BuildEnvSpec(
            name="local_build", build_env_type="local",
            description="本地构建", work_dir="/tmp/work",
            variables={"CC": "gcc"},
        )
        entry = svc.register_build_env(spec)
        assert entry["build_env_type"] == "local"
        got = svc.get_build_env("local_build")
        assert got is not None
        assert got.variables["CC"] == "gcc"

    def test_register_build_env_remote(self, svc):
        spec = BuildEnvSpec(
            name="remote_build", build_env_type="remote",
            host="10.0.0.1", port=22, user="builder",
        )
        svc.register_build_env(spec)
        got = svc.get_build_env("remote_build")
        assert got is not None
        assert got.host == "10.0.0.1"

    def test_register_build_env_empty_name_raises(self, svc):
        with pytest.raises(ValidationError, match="name"):
            svc.register_build_env(BuildEnvSpec(name=""))

    def test_register_build_env_invalid_type_raises(self, svc):
        with pytest.raises(ValidationError, match="不支持"):
            svc.register_build_env(BuildEnvSpec(name="x", build_env_type="cloud"))

    def test_list_build_envs(self, svc):
        svc.register_build_env(BuildEnvSpec(name="a"))
        svc.register_build_env(BuildEnvSpec(name="b"))
        assert len(svc.list_build_envs()) == 2

    def test_remove_build_env(self, svc):
        svc.register_build_env(BuildEnvSpec(name="tmp"))
        assert svc.remove_build_env("tmp") is True
        assert svc.remove_build_env("tmp") is False

    # ---- 执行环境 CRUD ----

    def test_register_exe_env_eda(self, svc):
        spec = ExeEnvSpec(
            name="eda_env", exe_env_type="eda",
            api_url="https://eda.example.com/api",
            tools={"vcs": ToolSpec(name="vcs", version="2023.03",
                                   install_path="/eda/vcs")},
            licenses={"LM_LICENSE_FILE": "1234@lic"},
        )
        entry = svc.register_exe_env(spec)
        assert entry["exe_env_type"] == "eda"
        got = svc.get_exe_env("eda_env")
        assert got is not None
        assert "vcs" in got.tools

    def test_register_exe_env_fpga(self, svc):
        spec = ExeEnvSpec(
            name="fpga_env", exe_env_type="fpga",
            api_url="https://fpga.example.com/api",
        )
        svc.register_exe_env(spec)
        got = svc.get_exe_env("fpga_env")
        assert got is not None
        assert got.exe_env_type == "fpga"

    def test_register_exe_env_empty_name_raises(self, svc):
        with pytest.raises(ValidationError, match="name"):
            svc.register_exe_env(ExeEnvSpec(name=""))

    def test_register_exe_env_invalid_type_raises(self, svc):
        with pytest.raises(ValidationError, match="不支持"):
            svc.register_exe_env(ExeEnvSpec(name="x", exe_env_type="gpu"))

    def test_list_exe_envs(self, svc):
        svc.register_exe_env(ExeEnvSpec(name="a", api_url="https://a"))
        svc.register_exe_env(ExeEnvSpec(name="b", api_url="https://b"))
        assert len(svc.list_exe_envs()) == 2

    def test_remove_exe_env(self, svc):
        svc.register_exe_env(ExeEnvSpec(name="tmp", api_url="https://t"))
        assert svc.remove_exe_env("tmp") is True
        assert svc.remove_exe_env("tmp") is False

    # ---- 统一列表 ----

    def test_list_all(self, svc):
        svc.register_build_env(BuildEnvSpec(name="build1"))
        svc.register_exe_env(ExeEnvSpec(name="exe1", api_url="https://exe"))
        all_envs = svc.list_all()
        assert len(all_envs) == 2
        categories = {e["category"] for e in all_envs}
        assert categories == {"build", "exe"}

    # ---- 生命周期 ----

    def test_apply_local_build(self, svc, tmp_path):
        work = str(tmp_path / "build_work")
        svc.register_build_env(BuildEnvSpec(
            name="local", build_env_type="local",
            work_dir=work, variables={"MY_VAR": "hello"},
        ))
        session = svc.apply(build_env_name="local")
        assert session.status == "applied"
        assert session.resolved_vars["MY_VAR"] == "hello"
        assert session.work_dir == work

    def test_apply_remote_build(self, svc):
        svc.register_build_env(BuildEnvSpec(
            name="remote", build_env_type="remote",
            host="10.0.0.1", user="admin",
        ))
        session = svc.apply(build_env_name="remote")
        assert session.status == "applied"
        assert session.resolved_vars["REMOTE_HOST"] == "10.0.0.1"

    def test_apply_exe_env_eda(self, svc):
        svc.register_exe_env(ExeEnvSpec(
            name="sim", exe_env_type="eda",
            api_url="https://eda/api", api_token="tok123",
            variables={"WAVE": "on"},
            licenses={"LIC": "5678@host"},
        ))
        session = svc.apply(exe_env_name="sim")
        assert session.status == "applied"
        assert session.resolved_vars["API_URL"] == "https://eda/api"
        assert session.resolved_vars["API_TOKEN"] == "tok123"
        assert session.resolved_vars["WAVE"] == "on"
        assert session.resolved_vars["LIC"] == "5678@host"

    def test_apply_nonexistent_raises(self, svc):
        with pytest.raises(CaseNotFoundError, match="不存在"):
            svc.apply(build_env_name="no_such")

    def test_release(self, svc, tmp_path):
        svc.register_build_env(BuildEnvSpec(
            name="rel_env", work_dir=str(tmp_path / "w"),
        ))
        session = svc.apply(build_env_name="rel_env")
        assert session.status == "applied"
        svc.release(session)
        assert session.status == "released"

    def test_timeout(self, svc, tmp_path):
        svc.register_build_env(BuildEnvSpec(
            name="to_env", work_dir=str(tmp_path / "w"),
        ))
        session = svc.apply(build_env_name="to_env")
        svc.timeout(session)
        assert session.status == "timeout"

    def test_invalid(self, svc, tmp_path):
        svc.register_build_env(BuildEnvSpec(
            name="inv_env", work_dir=str(tmp_path / "w"),
        ))
        session = svc.apply(build_env_name="inv_env")
        svc.invalid(session)
        assert session.status == "invalid"

    def test_execute_in(self, svc, tmp_path):
        svc.register_build_env(BuildEnvSpec(
            name="exec_env", work_dir=str(tmp_path),
        ))
        session = svc.apply(build_env_name="exec_env")
        result = svc.execute_in(session, "echo hello", timeout=10)
        assert result["success"] is True
        assert "hello" in result["stdout"]

    def test_execute_timeout(self, svc, tmp_path):
        svc.register_build_env(BuildEnvSpec(
            name="slow", work_dir=str(tmp_path),
        ))
        session = svc.apply(build_env_name="slow")
        result = svc.execute_in(session, "sleep 10", timeout=1)
        assert result["success"] is False
        assert "超时" in result["stderr"]

    def test_execute_after_release_raises(self, svc, tmp_path):
        svc.register_build_env(BuildEnvSpec(
            name="rel", work_dir=str(tmp_path),
        ))
        session = svc.apply(build_env_name="rel")
        svc.release(session)
        with pytest.raises(ValidationError, match="不可用"):
            svc.execute_in(session, "echo fail")

    def test_sessions_tracking(self, svc, tmp_path):
        svc.register_build_env(BuildEnvSpec(
            name="track", work_dir=str(tmp_path),
        ))
        session = svc.apply(build_env_name="track")
        sessions = svc.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == session.session_id
        got = svc.get_session(session.session_id)
        assert got is session
        svc.release(session)
        assert svc.list_sessions() == []
