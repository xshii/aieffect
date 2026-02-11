"""日志检查器测试"""

from pathlib import Path

import yaml

from framework.core.log_checker import LogChecker


def _create_rules(tmp_path: Path, rules: list[dict]) -> str:
    path = tmp_path / "rules.yml"
    path.write_text(yaml.dump({"rules": rules}))
    return str(path)


class TestLogChecker:
    def test_required_pass(self, tmp_path: Path) -> None:
        rules_file = _create_rules(tmp_path, [
            {"name": "done", "pattern": "Simulation complete", "type": "required"},
        ])
        checker = LogChecker(rules_file=rules_file)
        report = checker.check_text("INFO: Simulation complete at 1000ns")
        assert report.success is True
        assert report.passed_rules == 1

    def test_required_fail(self, tmp_path: Path) -> None:
        rules_file = _create_rules(tmp_path, [
            {"name": "done", "pattern": "Simulation complete", "type": "required"},
        ])
        checker = LogChecker(rules_file=rules_file)
        report = checker.check_text("ERROR: something went wrong")
        assert report.success is False
        assert report.failed_rules == 1

    def test_forbidden_pass(self, tmp_path: Path) -> None:
        rules_file = _create_rules(tmp_path, [
            {"name": "no_fatal", "pattern": "FATAL", "type": "forbidden"},
        ])
        checker = LogChecker(rules_file=rules_file)
        report = checker.check_text("INFO: all good\nWARN: minor issue")
        assert report.success is True

    def test_forbidden_fail(self, tmp_path: Path) -> None:
        rules_file = _create_rules(tmp_path, [
            {"name": "no_fatal", "pattern": "FATAL", "type": "forbidden"},
        ])
        checker = LogChecker(rules_file=rules_file)
        report = checker.check_text("UVM_FATAL : assertion failed")
        assert report.success is False
        assert report.failed_rules == 1

    def test_mixed_rules(self, tmp_path: Path) -> None:
        rules_file = _create_rules(tmp_path, [
            {"name": "done", "pattern": "PASS", "type": "required"},
            {"name": "no_err", "pattern": "ERROR", "type": "forbidden"},
        ])
        checker = LogChecker(rules_file=rules_file)

        # 全通过
        r1 = checker.check_text("TEST PASS")
        assert r1.success is True

        # required 通过，forbidden 失败
        r2 = checker.check_text("TEST PASS\nERROR: oops")
        assert r2.success is False
        assert r2.passed_rules == 1
        assert r2.failed_rules == 1

    def test_check_file(self, tmp_path: Path) -> None:
        rules_file = _create_rules(tmp_path, [
            {"name": "done", "pattern": "complete", "type": "required"},
        ])
        log = tmp_path / "sim.log"
        log.write_text("Simulation complete")

        checker = LogChecker(rules_file=rules_file)
        report = checker.check_file(str(log))
        assert report.success is True

    def test_check_file_not_found(self, tmp_path: Path) -> None:
        rules_file = _create_rules(tmp_path, [])
        checker = LogChecker(rules_file=rules_file)
        report = checker.check_file(str(tmp_path / "nonexist.log"))
        assert report.success is False

    def test_no_rules_file(self, tmp_path: Path) -> None:
        checker = LogChecker(rules_file=str(tmp_path / "nonexist.yml"))
        report = checker.check_text("anything")
        assert report.total_rules == 0
        assert report.success is True
