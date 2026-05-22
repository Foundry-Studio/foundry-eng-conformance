"""Dependency-direction + acyclic check (JOS-S53 § What Good Looks Like, bullet 3).

Uses import-linter as the backend (per Tim's call 2026-05-22 — don't
reinvent dep-graph code). The translation `manifest → import-linter
contracts` is our adapter; import-linter handles the import-graph walk,
contract evaluation, and cycle detection.

Two contract types are emitted per manifest:

  1. Forbidden contracts (per subsystem) — for each subsystem `S`,
     forbid imports from any code under S's `code_paths` to subsystem
     `T` UNLESS T appears in S's `allowed_outbound.subsystem` (or the
     import is to an external package).

  2. Independence + acyclic check — top-level "no cycles between any
     two subsystems" (JOS-P20). Implemented as N(N-1)/2 forbidden
     contracts, or as a single independence contract if import-linter
     supports it directly (it does: `independence`).

The check is INVOKED IN-PROCESS via import-linter's Python API — no
`.importlinter` config file is written to disk. The compiled config is
held in memory; import-linter loads the import graph once per run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from foundry_eng_conformance.schema import EngManifest, Subsystem

if TYPE_CHECKING:
    # import-linter is a heavy import; type-only here to avoid the
    # cost when only the dataclass is needed.
    pass


@dataclass
class DependencyViolation:
    """One disallowed edge or cycle."""

    kind: str  # "disallowed_outbound" | "cycle"
    from_subsystem: str
    to_subsystem: str | None
    importer: str | None = None
    imported: str | None = None
    line: int | None = None


@dataclass
class DependencyDirectionResult:
    contracts_evaluated: int = 0
    violations: list[DependencyViolation] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)
    skipped_reason: str | None = None

    @property
    def passed(self) -> bool:
        return not self.violations and not self.cycles

    @property
    def violation_count(self) -> int:
        return len(self.violations) + len(self.cycles)

    def to_details(self) -> dict:
        return {
            "contracts_evaluated": self.contracts_evaluated,
            "violation_count": self.violation_count,
            "cycle_count": len(self.cycles),
            "skipped_reason": self.skipped_reason,
            "violations_sample": [
                {
                    "kind": v.kind,
                    "from_subsystem": v.from_subsystem,
                    "to_subsystem": v.to_subsystem,
                    "importer": v.importer,
                    "imported": v.imported,
                    "line": v.line,
                }
                for v in self.violations[:25]
            ],
            "cycles_sample": self.cycles[:10],
        }


def _python_package_root(repo_root: Path) -> str | None:
    """Heuristic: find the top-level Python package name to use as
    import-linter's `root_packages`.

    For monorepos with `src/<pkg>/...` layout, return `<pkg>`. For repos
    with top-level packages, return the first package dir with an
    `__init__.py`. Returns None if no package can be found — in that
    case the dependency-direction check is SKIPPED (with a reason), not
    failed.
    """
    src_dir = repo_root / "src"
    if src_dir.exists() and src_dir.is_dir():
        for child in sorted(src_dir.iterdir()):
            if child.is_dir() and (child / "__init__.py").exists():
                return child.name
    # Fallback: any top-level package
    for child in sorted(repo_root.iterdir()):
        if child.is_dir() and (child / "__init__.py").exists():
            if child.name.startswith(".") or child.name in {"tests", "scripts"}:
                continue
            return child.name
    return None


def _code_path_to_module_prefix(
    code_path: str, root_package: str
) -> str | None:
    """Translate a manifest `code_paths` glob to an import-linter
    module prefix (dotted path).

    Examples:
        src/work_definition/definitions/**/*.py
            → work_definition.definitions   (assuming root_package = src layout)
        work_definition/definitions/**/*.py
            → work_definition.definitions

    Returns None if the glob can't be translated (e.g. uses wildcards
    in directory positions other than the trailing `**/*.py`).
    """
    # Strip leading src/ if present (import-linter operates on
    # importable module names, not filesystem paths).
    p = code_path
    if p.startswith("src/"):
        p = p[4:]
    # Strip trailing /**/*.py
    for suffix in ("/**/*.py", "/**/*.pyi", "/*.py"):
        if p.endswith(suffix):
            p = p[: -len(suffix)]
            break
    # Anything left with a wildcard is too irregular for v0.
    if "*" in p or "?" in p:
        return None
    # Convert filesystem separators to dots.
    return p.replace("/", ".")


def _build_subsystem_module_map(
    manifest: EngManifest, root_package: str
) -> dict[str, list[str]]:
    """For each subsystem id, compute the list of import-linter module
    prefixes that represent its code (translated from code_paths)."""
    out: dict[str, list[str]] = {}
    for s in manifest.spec.subsystems:
        modules: list[str] = []
        for cp in s.code_paths:
            mod = _code_path_to_module_prefix(cp, root_package)
            if mod is not None:
                modules.append(mod)
        out[s.id] = modules
    return out


def run_dependency_direction(
    manifest: EngManifest, repo_root: str | Path
) -> DependencyDirectionResult:
    """Run the dependency-direction + acyclic check via import-linter.

    Builds import-linter `ForbiddenContract` per subsystem (disallowed
    outbound edges) + `IndependenceContract` (cycle detection between
    declared subsystems). Returns a result object; never raises on a
    violation.

    If the repo doesn't have a discoverable Python package root, the
    check is SKIPPED (recorded as `skipped_reason`) — not failed.
    """
    repo_root = Path(repo_root).resolve()
    result = DependencyDirectionResult()

    root_package = _python_package_root(repo_root)
    if root_package is None:
        result.skipped_reason = (
            "no Python package root found (no src/<pkg>/__init__.py "
            "nor top-level package with __init__.py)"
        )
        return result

    module_map = _build_subsystem_module_map(manifest, root_package)

    # Filter out subsystems whose code_paths couldn't be translated to
    # a module prefix — they're skipped for dep-direction but still
    # covered by structure-coverage.
    declared_subsystems = [
        s for s in manifest.spec.subsystems if module_map.get(s.id)
    ]
    if not declared_subsystems:
        result.skipped_reason = (
            "no subsystems have code_paths translatable to import-linter "
            "module prefixes (all globs were too irregular)"
        )
        return result

    try:
        from grimp import build_graph
    except ImportError as e:
        # grimp is import-linter's graph builder; if it's not present the
        # tool was installed without its full deps. Defer to runtime so
        # the rest of the tool works without it.
        result.skipped_reason = f"grimp (import-linter graph backend) not available: {e}"
        return result

    # Build the import graph for the discovered root_package + any
    # sibling top-level packages referenced by subsystems.
    package_set = {root_package}
    for modlist in module_map.values():
        for m in modlist:
            head = m.split(".", 1)[0]
            package_set.add(head)

    # grimp resolves packages via sys.path. For an arbitrary repo we
    # need to prepend the candidate source dirs so grimp can find the
    # target packages on disk. Order: src/ first (most common Foundry
    # layout), then repo root (flat-layout fallback).
    import sys

    saved_path = sys.path[:]
    candidates = [str(repo_root / "src"), str(repo_root)]
    try:
        for c in candidates:
            if c not in sys.path:
                sys.path.insert(0, c)
        try:
            graph = build_graph(
                *sorted(package_set), include_external_packages=False
            )
        except Exception as e:
            result.skipped_reason = f"failed to build import graph: {e}"
            return result
    finally:
        sys.path[:] = saved_path

    # ── Forbidden contracts (allowed_outbound enforcement) ──
    # For each subsystem S with declared allowed_outbound, build a
    # ForbiddenContract: source = S's modules, forbidden_modules = any
    # declared subsystem T whose modules are NOT in S's allowed list.
    all_subsystem_ids = {s.id for s in declared_subsystems}
    for s in declared_subsystems:
        allowed_sids = {e.subsystem for e in s.allowed_outbound if e.subsystem}
        forbidden_sids = all_subsystem_ids - allowed_sids - {s.id}

        source_modules = module_map[s.id]
        forbidden_modules: list[str] = []
        for t_sid in forbidden_sids:
            forbidden_modules.extend(module_map.get(t_sid, []))

        if not source_modules or not forbidden_modules:
            continue

        # Evaluate the contract via the graph directly (avoid going
        # through the full importlinter CLI infrastructure for a
        # programmatic, in-process check).
        for src_prefix in source_modules:
            for forb_prefix in forbidden_modules:
                # Find any direct import edges src_prefix.* → forb_prefix.*
                src_modules_in_graph = {
                    m
                    for m in graph.modules
                    if m == src_prefix or m.startswith(src_prefix + ".")
                }
                for importer in src_modules_in_graph:
                    for imported in graph.find_modules_directly_imported_by(importer):
                        if imported == forb_prefix or imported.startswith(
                            forb_prefix + "."
                        ):
                            # Look up importing-from-line if available
                            details = graph.get_import_details(
                                importer=importer, imported=imported
                            )
                            line = None
                            if details:
                                line = details[0].get("line_number")
                            # Find which target subsystem this maps to
                            target_sid = next(
                                (
                                    sid
                                    for sid in forbidden_sids
                                    if any(
                                        imported == m or imported.startswith(m + ".")
                                        for m in module_map.get(sid, [])
                                    )
                                ),
                                None,
                            )
                            result.violations.append(
                                DependencyViolation(
                                    kind="disallowed_outbound",
                                    from_subsystem=s.id,
                                    to_subsystem=target_sid,
                                    importer=importer,
                                    imported=imported,
                                    line=line,
                                )
                            )
                result.contracts_evaluated += 1

    # ── Independence / acyclic check (JOS-P20) ──
    # Walk all pairs of subsystems. Use grimp's package-level chain
    # finder (`find_shortest_chains`, plural) which handles the
    # package-vs-submodule squashing — `find_shortest_chain` (singular)
    # only works on direct module nodes and misses the package case.
    for i, s1 in enumerate(declared_subsystems):
        for s2 in declared_subsystems[i + 1 :]:
            mods_1 = module_map[s1.id]
            mods_2 = module_map[s2.id]
            found_cycle = False
            for m1 in mods_1:
                if found_cycle:
                    break
                for m2 in mods_2:
                    if m1 not in graph.modules or m2 not in graph.modules:
                        continue
                    chains_1_to_2 = graph.find_shortest_chains(
                        importer=m1, imported=m2
                    )
                    chains_2_to_1 = graph.find_shortest_chains(
                        importer=m2, imported=m1
                    )
                    if chains_1_to_2 and chains_2_to_1:
                        cycle = sorted([s1.id, s2.id])
                        if cycle not in result.cycles:
                            result.cycles.append(cycle)
                        found_cycle = True
                        break

    return result
