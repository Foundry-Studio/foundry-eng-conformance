"""Tests for the CLI — exit codes + mode flag behavior (Atlas review)."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from foundry_eng_conformance.cli import main


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# x\n", encoding="utf-8")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestCLIExitCodes:
    def test_help_exits_zero(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0

    def test_check_missing_manifest_exits_2(self, runner, tmp_path):
        result = runner.invoke(main, ["check", "--repo", str(tmp_path)])
        assert result.exit_code == 2
        assert "manifest not found" in result.output.lower()

    def test_validate_missing_manifest_exits_2(self, runner, tmp_path):
        result = runner.invoke(main, ["validate", "--repo", str(tmp_path)])
        assert result.exit_code == 2

    def test_check_clean_repo_exits_zero(self, runner, tmp_path, write_manifest):
        write_manifest()
        _touch(tmp_path / "src" / "alpha" / "service.py")
        _touch(tmp_path / "src" / "beta" / "worker.py")
        result = runner.invoke(
            main,
            ["check", "--repo", str(tmp_path), "--mode", "enforce",
             "--no-emit-evidence"],
        )
        # Should pass — both files match declared subsystems
        assert result.exit_code == 0


class TestModeFlag:
    """Atlas review 2026-05-22: --mode=report ALWAYS exits 0 even on
    violations; --mode=enforce exits non-zero on any fail."""

    def test_report_mode_exits_zero_on_violation(
        self, runner, tmp_path, write_manifest
    ):
        write_manifest()
        _touch(tmp_path / "src" / "alpha" / "service.py")
        # Rogue file: uncovered
        _touch(tmp_path / "src" / "rogue" / "thing.py")
        result = runner.invoke(
            main,
            ["check", "--repo", str(tmp_path), "--mode", "report",
             "--no-emit-evidence"],
        )
        # Violations present but report mode → exit 0
        assert result.exit_code == 0
        # Output should mention the violation
        assert "rogue" in result.output.lower() or "uncovered" in result.output.lower()

    def test_enforce_mode_exits_one_on_violation(
        self, runner, tmp_path, write_manifest
    ):
        write_manifest()
        _touch(tmp_path / "src" / "alpha" / "service.py")
        _touch(tmp_path / "src" / "rogue" / "thing.py")
        result = runner.invoke(
            main,
            ["check", "--repo", str(tmp_path), "--mode", "enforce",
             "--no-emit-evidence"],
        )
        assert result.exit_code == 1

    def test_report_is_default(self, runner, tmp_path, write_manifest):
        """No --mode flag should default to report."""
        write_manifest()
        _touch(tmp_path / "src" / "alpha" / "service.py")
        _touch(tmp_path / "src" / "rogue" / "thing.py")
        result = runner.invoke(
            main,
            ["check", "--repo", str(tmp_path), "--no-emit-evidence"],
        )
        # Default = report → exit 0 on violation
        assert result.exit_code == 0


class TestEvidenceEmission:
    def test_evidence_written_by_default(self, runner, tmp_path, write_manifest):
        write_manifest()
        _touch(tmp_path / "src" / "alpha" / "service.py")
        _touch(tmp_path / "src" / "beta" / "worker.py")
        result = runner.invoke(
            main, ["check", "--repo", str(tmp_path)]
        )
        assert result.exit_code == 0
        # Evidence dir should exist under <repo>/evidence/<today>/
        evidence_dirs = list((tmp_path / "evidence").iterdir())
        assert len(evidence_dirs) == 1
        evidence_files = list(evidence_dirs[0].iterdir())
        assert any(f.name == "eng-conformance.jsonl" for f in evidence_files)

    def test_no_emit_evidence_flag_skips_write(self, runner, tmp_path, write_manifest):
        write_manifest()
        _touch(tmp_path / "src" / "alpha" / "service.py")
        _touch(tmp_path / "src" / "beta" / "worker.py")
        result = runner.invoke(
            main, ["check", "--repo", str(tmp_path), "--no-emit-evidence"]
        )
        assert result.exit_code == 0
        # No evidence dir created
        assert not (tmp_path / "evidence").exists()


class TestValidateCommand:
    def test_valid_manifest_exits_zero(self, runner, tmp_path, write_manifest):
        write_manifest()
        result = runner.invoke(main, ["validate", "--repo", str(tmp_path)])
        assert result.exit_code == 0
        assert "manifest ok" in result.output.lower()

    def test_invalid_manifest_exits_two(self, runner, tmp_path, write_manifest):
        write_manifest({"schema_version": "0.99.0"})
        result = runner.invoke(main, ["validate", "--repo", str(tmp_path)])
        assert result.exit_code == 2
