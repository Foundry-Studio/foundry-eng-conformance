"""Conformance checks.

Two checks implement JOS-S53:
  - structure_coverage: every code unit maps to exactly one declared
    subsystem (our own logic over code_paths globs).
  - dependency_direction: actual import graph respects allowed_outbound +
    acyclic (import-linter backend; manifest compiles to its contracts).
"""

from foundry_eng_conformance.checks.structure_coverage import (
    StructureCoverageResult,
    run_structure_coverage,
)

__all__ = ["StructureCoverageResult", "run_structure_coverage"]
