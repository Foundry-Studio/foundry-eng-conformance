"""Human-readable output for CLI runs.

The CLI calls these to format check results for the terminal. Evidence
emission is separate (machine-readable JSONL); these formatters are
purely cosmetic for humans watching CI logs.
"""

from __future__ import annotations

from foundry_eng_conformance.checks.dependency_direction import (
    DependencyDirectionResult,
)
from foundry_eng_conformance.checks.structure_coverage import (
    StructureCoverageResult,
)


def format_structure_coverage(res: StructureCoverageResult) -> str:
    lines = ["== Structure coverage =="]
    lines.append(f"  Scanned: {res.files_scanned} .py files")
    lines.append(f"  Covered: {res.files_covered}")
    lines.append(f"  Exempt:  {res.files_exempt}")
    if res.files_deferred:
        lines.append(f"  Deferred (out-of-scope this pass): {res.files_deferred}")
    if res.catch_all_under_retire:
        lines.append(
            f"  Catch-all (under retire, not a violation): "
            f"{len(res.catch_all_under_retire)}"
        )
    if res.ambiguous:
        lines.append(f"  AMBIGUOUS: {len(res.ambiguous)}")
        for path, sids in list(res.ambiguous.items())[:10]:
            lines.append(f"    {path}  matches: {sids}")
        if len(res.ambiguous) > 10:
            lines.append(f"    ... +{len(res.ambiguous) - 10} more")
    if res.uncovered:
        lines.append(f"  UNCOVERED (catch-all violation): {len(res.uncovered)}")
        for path in res.uncovered[:10]:
            lines.append(f"    {path}")
        if len(res.uncovered) > 10:
            lines.append(f"    ... +{len(res.uncovered) - 10} more")
    status = "PASS" if res.passed else f"FAIL ({res.violation_count} violations)"
    lines.append(f"  Status: {status}")
    return "\n".join(lines)


def format_dependency_direction(res: DependencyDirectionResult) -> str:
    lines = ["== Dependency direction + acyclic =="]
    if res.skipped_reason:
        lines.append(f"  SKIPPED: {res.skipped_reason}")
        return "\n".join(lines)
    lines.append(f"  Contracts evaluated: {res.contracts_evaluated}")
    if res.violations:
        lines.append(f"  Disallowed-outbound violations: {len(res.violations)}")
        for v in res.violations[:10]:
            target = v.to_subsystem or "<external>"
            loc = f":{v.line}" if v.line else ""
            lines.append(
                f"    {v.from_subsystem} -> {target}  "
                f"({v.importer}{loc} imports {v.imported})"
            )
        if len(res.violations) > 10:
            lines.append(f"    ... +{len(res.violations) - 10} more")
    if res.cycles:
        lines.append(f"  Cycles: {len(res.cycles)}")
        for cyc in res.cycles[:5]:
            lines.append(f"    {' <-> '.join(cyc)}")
    status = "PASS" if res.passed else f"FAIL ({res.violation_count} violations)"
    lines.append(f"  Status: {status}")
    return "\n".join(lines)
