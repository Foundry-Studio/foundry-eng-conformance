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


class TestDeferredPaths:
    """v0.1.1 — deferred_paths field (out-of-scope-this-pass, distinct from exempt)."""

    def test_deferred_file_tracked_separately(self, tmp_path, write_manifest):
        _touch(tmp_path / "src" / "alpha" / "service.py")
        _touch(tmp_path / "platform" / "thing.py")   # deferred
        path = write_manifest(
            {"spec": {
                "deferred_paths": [
                    {
                        "path": "platform/**/*.py",
                        "reason": "Deferred to follow-on reorg pass",
                        "until": "2026-09-01",
                    }
                ]
            }}
        )
        m = load_manifest(path)
        result = run_structure_coverage(m, tmp_path)

        assert result.files_deferred == 1
        assert "platform/thing.py" in result.deferred
        assert "platform/thing.py" not in result.uncovered
        assert result.passed   # deferred files don't count as violations

    def test_deferred_takes_precedence_over_subsystem_match(
        self, tmp_path, write_manifest
    ):
        """A file matching BOTH deferred + subsystem code_paths is treated as deferred."""
        _touch(tmp_path / "src" / "alpha" / "deferred_thing.py")
        path = write_manifest(
            {"spec": {
                "deferred_paths": [
                    {
                        "path": "src/alpha/deferred_*.py",
                        "reason": "specific file deferred",
                    }
                ]
            }}
        )
        m = load_manifest(path)
        result = run_structure_coverage(m, tmp_path)

        assert "src/alpha/deferred_thing.py" in result.deferred
        assert "src/alpha/deferred_thing.py" not in result.covered

    def test_exempt_takes_precedence_over_deferred(self, tmp_path, write_manifest):
        """exempt_paths is the highest priority (genuine non-subsystem files)."""
        _touch(tmp_path / "tests" / "test_alpha.py")
        path = write_manifest(
            {"spec": {
                "deferred_paths": [
                    {"path": "tests/**/*.py", "reason": "would conflict"}
                ]
            }}
        )
        m = load_manifest(path)
        result = run_structure_coverage(m, tmp_path)

        # exempt_paths default covers tests/, so file is exempt (not deferred)
        assert result.files_exempt >= 1
        assert "tests/test_alpha.py" not in result.deferred

    def test_deferred_without_until_date_accepted(self, tmp_path, write_manifest):
        """`until` is optional — deferred can be open-ended."""
        _touch(tmp_path / "src" / "alpha" / "service.py")
        _touch(tmp_path / "tools" / "scratch.py")
        path = write_manifest(
            {"spec": {
                "deferred_paths": [
                    {"path": "tools/**/*.py", "reason": "ops scripts"}
                ]
            }}
        )
        m = load_manifest(path)
        result = run_structure_coverage(m, tmp_path)
        assert result.files_deferred == 1
