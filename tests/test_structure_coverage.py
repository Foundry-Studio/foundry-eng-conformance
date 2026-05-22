"""Tests for the structure-coverage check."""

from __future__ import annotations

from pathlib import Path

from foundry_eng_conformance.checks.structure_coverage import (
    run_structure_coverage,
)
from foundry_eng_conformance.schema import load_manifest


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# placeholder\n", encoding="utf-8")


class TestStructureCoverage:
    def test_all_files_covered(self, tmp_path, write_manifest):
        # Create files matching declared subsystems
        _touch(tmp_path / "src" / "alpha" / "service.py")
        _touch(tmp_path / "src" / "alpha" / "nested" / "thing.py")
        _touch(tmp_path / "src" / "beta" / "worker.py")
        path = write_manifest()
        m = load_manifest(path)

        result = run_structure_coverage(m, tmp_path)

        assert result.passed
        assert result.files_covered == 3
        assert not result.uncovered
        assert not result.ambiguous

    def test_uncovered_file_flagged(self, tmp_path, write_manifest):
        _touch(tmp_path / "src" / "alpha" / "service.py")
        _touch(tmp_path / "src" / "gamma" / "rogue.py")  # not declared
        path = write_manifest()
        m = load_manifest(path)

        result = run_structure_coverage(m, tmp_path)

        assert not result.passed
        assert "src/gamma/rogue.py" in result.uncovered
        assert result.files_covered == 1

    def test_exempt_paths_skipped(self, tmp_path, write_manifest):
        _touch(tmp_path / "src" / "alpha" / "service.py")
        _touch(tmp_path / "tests" / "test_alpha.py")
        _touch(tmp_path / "scripts" / "do_thing.py")
        _touch(tmp_path / "migrations" / "versions" / "001_init.py")
        _touch(tmp_path / "src" / "alpha" / "__init__.py")
        path = write_manifest()
        m = load_manifest(path)

        result = run_structure_coverage(m, tmp_path)

        assert result.passed
        assert result.files_exempt >= 4  # tests, scripts, migrations, __init__
        assert result.files_covered == 1  # only service.py counted

    def test_catch_all_bucket_separated(self, tmp_path, write_manifest):
        """Files under a declared catch_all_buckets entry are reported
        separately, not as a hard uncovered violation."""
        _touch(tmp_path / "src" / "alpha" / "service.py")
        _touch(tmp_path / "src" / "legacy" / "stuff.py")
        path = write_manifest(
            {"spec": {
                "catch_all_buckets": [
                    {
                        "path": "src/legacy/**/*.py",
                        "rationale": "Legacy; under retire",
                        "sunset_target": "2026-09-01",
                    }
                ]
            }}
        )
        m = load_manifest(path)

        result = run_structure_coverage(m, tmp_path)

        assert not result.uncovered  # not a hard violation
        assert "src/legacy/stuff.py" in result.catch_all_under_retire
        assert result.passed  # catch-all-under-retire doesn't fail the check

    def test_ambiguous_when_two_subsystems_claim_same_file(
        self, tmp_path, write_manifest
    ):
        _touch(tmp_path / "src" / "shared" / "common.py")
        path = write_manifest(
            {"spec": {"subsystems": [
                {
                    "id": "alpha",
                    "title": "Alpha",
                    "owner": "tim",
                    "lifecycle_stage": "adopt",
                    "code_paths": ["src/shared/**/*.py"],
                    "published_interfaces": {"python": ["alpha.x"]},
                },
                {
                    "id": "beta",
                    "title": "Beta",
                    "owner": "tim",
                    "lifecycle_stage": "adopt",
                    "code_paths": ["src/shared/**/*.py"],  # overlap
                    "allowed_outbound": [{"subsystem": "alpha"}],
                },
            ]}}
        )
        m = load_manifest(path)
        result = run_structure_coverage(m, tmp_path)

        assert not result.passed
        assert "src/shared/common.py" in result.ambiguous
        assert set(result.ambiguous["src/shared/common.py"]) == {"alpha", "beta"}

    def test_glob_recursive_match(self, tmp_path, write_manifest):
        """`src/alpha/**/*.py` should match arbitrary depth."""
        _touch(tmp_path / "src" / "alpha" / "a.py")
        _touch(tmp_path / "src" / "alpha" / "b" / "c.py")
        _touch(tmp_path / "src" / "alpha" / "b" / "c" / "d.py")
        path = write_manifest()
        m = load_manifest(path)
        result = run_structure_coverage(m, tmp_path)
        assert result.files_covered == 3
        assert result.passed

    def test_violation_count_excludes_catch_all(self, tmp_path, write_manifest):
        _touch(tmp_path / "src" / "alpha" / "service.py")
        _touch(tmp_path / "src" / "legacy" / "stuff.py")
        _touch(tmp_path / "src" / "rogue" / "thing.py")
        path = write_manifest(
            {"spec": {
                "catch_all_buckets": [
                    {"path": "src/legacy/**/*.py", "rationale": "x", "sunset_target": "2026-09-01"}
                ]
            }}
        )
        m = load_manifest(path)
        result = run_structure_coverage(m, tmp_path)
        # rogue/thing.py is uncovered; legacy/stuff.py is catch-all (not counted)
        assert result.violation_count == 1
        assert "src/rogue/thing.py" in result.uncovered
        assert "src/legacy/stuff.py" in result.catch_all_under_retire
