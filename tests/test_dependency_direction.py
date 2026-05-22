"""Tests for the dependency-direction + acyclic check.

These tests exercise the import-linter adapter on synthetic Python repo
trees laid out under tmp_path. The check is exercised end-to-end:
write code → load manifest → run check → assert violations/cycles.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from foundry_eng_conformance.checks.dependency_direction import (
    _code_path_to_module_prefix,
    run_dependency_direction,
)
from foundry_eng_conformance.schema import load_manifest


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_pkg(repo: Path, pkg_path: str, files: dict[str, str]) -> None:
    """Create a Python package tree under repo/src/<pkg_path>/.

    `pkg_path` is the dotted package name (e.g., "alpha" or "alpha.sub").
    `files` maps filename → content; `__init__.py` auto-created.
    """
    pkg_dir = repo / "src"
    for part in pkg_path.split("."):
        pkg_dir = pkg_dir / part
        (pkg_dir).mkdir(parents=True, exist_ok=True)
        init = pkg_dir / "__init__.py"
        if not init.exists():
            init.write_text("", encoding="utf-8")
    # Also ensure root package has __init__.py
    root = repo / "src" / pkg_path.split(".")[0]
    (root / "__init__.py").touch()
    for fname, content in files.items():
        _write(pkg_dir / fname, content)


class TestCodePathTranslation:
    def test_src_layout_to_module_prefix(self):
        assert (
            _code_path_to_module_prefix("src/alpha/**/*.py", "alpha")
            == "alpha"
        )
        assert (
            _code_path_to_module_prefix(
                "src/work_definition/definitions/**/*.py", "src"
            )
            == "work_definition.definitions"
        )

    def test_top_level_layout(self):
        assert (
            _code_path_to_module_prefix("alpha/**/*.py", "alpha")
            == "alpha"
        )

    def test_irregular_glob_unrtanslatable(self):
        assert (
            _code_path_to_module_prefix("src/*/foo/**/*.py", "src")
            is None
        )


class TestDependencyDirectionCheck:
    def test_no_package_root_skipped(self, tmp_path, write_manifest):
        # No __init__.py anywhere → no package root
        path = write_manifest()
        m = load_manifest(path)
        result = run_dependency_direction(m, tmp_path)
        assert result.skipped_reason is not None

    def test_clean_repo_passes(self, tmp_path, write_manifest):
        _make_pkg(tmp_path, "alpha", {"service.py": "X = 1\n"})
        _make_pkg(
            tmp_path,
            "beta",
            {"worker.py": "from alpha import service\nY = service.X\n"},
        )
        path = write_manifest()
        m = load_manifest(path)
        result = run_dependency_direction(m, tmp_path)
        # beta MAY import alpha per manifest; no cycle.
        assert result.passed, f"Expected pass, got violations: {result.violations}"

    def test_disallowed_outbound_detected(self, tmp_path, write_manifest):
        # alpha imports beta — but alpha's allowed_outbound only lists yaml,
        # NOT beta. Should be a violation.
        _make_pkg(
            tmp_path,
            "alpha",
            {"service.py": "from beta import worker\nX = worker\n"},
        )
        _make_pkg(tmp_path, "beta", {"worker.py": "Y = 1\n"})
        path = write_manifest()
        m = load_manifest(path)
        result = run_dependency_direction(m, tmp_path)
        assert not result.passed
        # At least one violation flagged from alpha → beta
        v_match = [
            v
            for v in result.violations
            if v.from_subsystem == "alpha" and v.to_subsystem == "beta"
        ]
        assert v_match, f"Expected alpha→beta violation, got: {result.violations}"

    def test_cycle_detected(self, tmp_path, write_manifest):
        # alpha imports beta AND beta imports alpha → cycle
        _make_pkg(
            tmp_path,
            "alpha",
            {"service.py": "from beta import worker\nX = 1\n"},
        )
        _make_pkg(
            tmp_path,
            "beta",
            {"worker.py": "from alpha import service\nY = 1\n"},
        )
        # Manifest must allow alpha → beta to isolate the cycle as the
        # finding (not the disallowed-outbound)
        path = write_manifest(
            {"spec": {"subsystems": [
                {
                    "id": "alpha",
                    "title": "A",
                    "owner": "tim",
                    "lifecycle_stage": "adopt",
                    "code_paths": ["src/alpha/**/*.py"],
                    "allowed_outbound": [{"subsystem": "beta"}],
                    "published_interfaces": {"python": ["alpha.service"]},
                },
                {
                    "id": "beta",
                    "title": "B",
                    "owner": "tim",
                    "lifecycle_stage": "adopt",
                    "code_paths": ["src/beta/**/*.py"],
                    "allowed_outbound": [{"subsystem": "alpha"}],
                    "published_interfaces": {"python": ["beta.worker"]},
                },
            ]}}
        )
        m = load_manifest(path)
        result = run_dependency_direction(m, tmp_path)
        assert result.cycles, f"Expected cycle detection, got: {result.cycles}"
        # The cycle is between alpha and beta
        cycle_set = {tuple(sorted(c)) for c in result.cycles}
        assert ("alpha", "beta") in cycle_set
