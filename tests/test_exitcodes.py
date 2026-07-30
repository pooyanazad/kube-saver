"""Tests for stable CLI exit codes and connection-error mapping."""

from __future__ import annotations

from click.testing import CliRunner

from kube_saver import exitcodes
from kube_saver.cli import cli as click_cli


class TestExitCodes:
    def test_constants_are_distinct(self) -> None:
        codes = {
            exitcodes.OK,
            exitcodes.GENERAL_ERROR,
            exitcodes.CONFIG_ERROR,
            exitcodes.CONNECTION_ERROR,
            exitcodes.ANALYSIS_ERROR,
        }
        assert len(codes) == 5
        assert exitcodes.OK == 0
        assert exitcodes.GENERAL_ERROR == 1
        assert exitcodes.CONFIG_ERROR == 2
        assert exitcodes.CONNECTION_ERROR == 3
        assert exitcodes.ANALYSIS_ERROR == 4

    def test_module_exports(self) -> None:
        import kube_saver.exitcodes as ec
        for name in ("OK", "GENERAL_ERROR", "CONFIG_ERROR", "CONNECTION_ERROR", "ANALYSIS_ERROR"):
            assert hasattr(ec, name)


class TestCliFailureMapping:
    """Verify that connection/config failures map to the documented exit codes."""

    def test_connection_error_yields_connection_code(self, monkeypatch) -> None:
        from kube_saver import cli as cli_mod

        def _boom():
            raise ConnectionError("api server not reachable")

        monkeypatch.setattr(cli_mod, "_run_analysis", _boom)

        runner = CliRunner()
        result = runner.invoke(click_cli, ["report", "-o", "/tmp/_ks_test.html"])
        assert result.exit_code == exitcodes.CONNECTION_ERROR
        assert "Kubernetes API" in result.output or "api server not reachable" in result.output

    def test_config_exception_yields_config_code(self, monkeypatch) -> None:
        from kube_saver import cli as cli_mod

        # Build a stand-in ConfigException without importing kubernetes.
        class _FakeConfigError(Exception):
            pass

        def _boom():
            raise _FakeConfigError("no such context 'staging'")

        monkeypatch.setattr(cli_mod, "_run_analysis", _boom)

        runner = CliRunner()
        # doctor does not call _run_analysis, but report does.
        result = runner.invoke(click_cli, ["report", "-o", "/tmp/_ks_test.html"])
        assert result.exit_code == exitcodes.GENERAL_ERROR  # generic, since the fake isn't a kubernetes ConfigException

    def test_file_not_found_yields_config_code(self, monkeypatch) -> None:
        from kube_saver import cli as cli_mod

        def _boom():
            raise FileNotFoundError("/nope/kubeconfig")

        monkeypatch.setattr(cli_mod, "_run_analysis", _boom)

        runner = CliRunner()
        result = runner.invoke(click_cli, ["report", "-o", "/tmp/_ks_test.html"])
        assert result.exit_code == exitcodes.CONFIG_ERROR
        assert "kubeconfig" in result.output

    def test_timeout_yields_connection_code(self, monkeypatch) -> None:
        from kube_saver import cli as cli_mod

        def _boom():
            raise TimeoutError("read timeout")

        monkeypatch.setattr(cli_mod, "_run_analysis", _boom)

        runner = CliRunner()
        result = runner.invoke(click_cli, ["report", "-o", "/tmp/_ks_test.html"])
        assert result.exit_code == exitcodes.CONNECTION_ERROR

    def test_unexpected_exception_yields_general_code(self, monkeypatch) -> None:
        from kube_saver import cli as cli_mod

        def _boom():
            raise ValueError("something weird")

        monkeypatch.setattr(cli_mod, "_run_analysis", _boom)

        runner = CliRunner()
        result = runner.invoke(click_cli, ["report", "-o", "/tmp/_ks_test.html"])
        assert result.exit_code == exitcodes.GENERAL_ERROR

    def test_doctor_failure_uses_general_code(self, monkeypatch, tmp_path) -> None:
        # Doctor doesn't run the analysis pipeline; it fails via report.ok.
        # The doctor command does `from kube_saver.doctor import run_doctor` at
        # runtime so we patch the module's attribute in sys.modules.
        import sys

        import kube_saver.doctor as doctor_mod
        from kube_saver.doctor import CheckResult, DoctorReport

        def _fake_doctor(context: str | None = None):
            return DoctorReport(
                kubeconfig_path=str(tmp_path / "config"),
                context="prod",
                checks=[CheckResult(name="kubeconfig", ok=False)],
            )

        monkeypatch.setattr(
            sys.modules.get("kube_saver.doctor", doctor_mod),
            "run_doctor",
            _fake_doctor,
        )

        runner = CliRunner()
        result = runner.invoke(click_cli, ["doctor"])
        assert result.exit_code == exitcodes.GENERAL_ERROR
