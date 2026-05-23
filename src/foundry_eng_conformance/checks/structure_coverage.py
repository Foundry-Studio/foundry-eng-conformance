"""Structure-coverage check (JOS-S53 § What Good Looks Like, bullet 2).

Walks the repo tree under each declared `code_paths` glob. For every
`*.py` file in the repo (relative to `repo_root`):

  - PASS — file matches exactly one subsystem's code_paths.
  - SKIP — file matches `spec.exempt_paths` (tests, scripts, etc.).
  - UNCOVERED — file matches zero subsystems and zero exempt_paths
    (catch-all violation).
  - AMBIGUOUS — file matches two or more subsystems (declaration overlap).

`spec.catch_all_buckets` is treated as a NAMED subset of UNCOVERED:
files matching a declared catch-all path are reported separately under
"catch_all_under_retire" with the bucket's `sunset_target` for tracking.

This is OUR logic (per Tim's explicit split — import-linter handles
dep-direction + cycles; structure-coverage is ours).
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path

from foundry_eng_conformance.schema import EngManifest


@dataclass
class StructureCoverageResult:
    """Outcome of one structure-coverage run."""

    files_scanned: int = 0
    files_covered: int = 0
    files_exempt: int = 0
    files_deferred: int = 0   # v0.1.1: out-of-scope-this-pass per spec.deferred_paths

    # path -> subsystem_id
    covered: dict[str, str] = field(default_factory=dict)
    # paths with no matching subsystem AND no exempt match
    uncovered: list[str] = field(default_factory=list)
    # path -> list of matching subsystem ids (len >= 2)
    ambiguous: dict[str, list[str]] = field(default_factory=dict)
    # path -> catch_all_buckets entry path that matched it
    catch_all_under_retire: dict[str, str] = field(default_factory=dict)
    # path -> deferred_paths entry path that matched it
    deferred: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.uncovered and not self.ambiguous

    @property
    def violation_count(self) -> int:
        # Catch-all-under-retire is tracked separately — not counted as a
        # violation here since it has an explicit sunset_target. The CLI
        # reporter surfaces it but it doesn't fail the check.
        return len(self.uncovered) + len(self.ambiguous)

    def to_details(self) -> dict:
        """Compact dict for evidence-record `details` field (AD-2)."""
        return {
            "files_scanned": self.files_scanned,
            "files_covered": self.files_covered,
            "files_exempt": self.files_exempt,
            "files_deferred": self.files_deferred,   # v0.1.1
            "files_uncovered": len(self.uncovered),
            "files_ambiguous": len(self.ambiguous),
            "files_catch_all_under_retire": len(self.catch_all_under_retire),
            # Cap the per-violation list at 25 entries to keep evidence
            # records bounded; full list is available in the human report.
            "uncovered_sample": self.uncovered[:25],
            "ambiguous_sample": {
                p: sids for p, sids in list(self.ambiguous.items())[:25]
            },
        }


def _matches_any(rel_path: str, globs: list[str]) -> bool:
    """True if `rel_path` matches any of the fnmatch-style globs.

    Glob `**` is translated to fnmatch's `*` semantics over path components
    by normalizing slashes and using fnmatch.fnmatchcase. fnmatch does NOT
    natively understand `**`, so we expand it: `a/**/b.py` becomes a
    pair of patterns `a/b.py` (zero intermediate dirs) + `a/*/b.py` +
    `a/*/*/b.py` etc. Practically we just translate `**` → `*` and rely
    on the file walker giving us the full relative path; `*` in fnmatch
    DOES NOT cross `/`, so we use a manual expansion.

    Simpler + correct approach: use Path.match which DOES handle `**`
    when invoked on a PurePath. Pathlib's match is `pattern.match(path)`
    semantics; we use PurePosixPath for cross-platform consistency.
    """
    from pathlib import PurePosixPath

    # Normalize to forward slashes for matching (manifest globs always
    # use /).
    normalized = rel_path.replace("\\", "/")
    pp = PurePosixPath(normalized)
    for g in globs:
        # pathlib's match returns True if the FINAL parts match; for
        # `src/foo/**/*.py` we want a recursive match. fnmatch handles
        # this correctly if we use the GLOB→regex translation manually.
        # The cleanest cross-version approach: use PurePosixPath.full_match
        # if available (3.13+), else fall back to manual.
        try:
            if pp.full_match(g):  # type: ignore[attr-defined]
                return True
        except AttributeError:
            # Python < 3.13 — fall back: replace ** with a recursive
            # placeholder, translate to fnmatch, evaluate.
            if _legacy_glob_match(normalized, g):
                return True
    return False


def _legacy_glob_match(path: str, pattern: str) -> bool:
    """Fallback ** glob matcher for Python < 3.13.

    Translates `a/**/b.py` to a regex equivalent and matches.
    """
    import re

    # Build a regex from the glob:
    #   **  -> .*       (any chars including /)
    #   *   -> [^/]*    (any chars except /)
    #   ?   -> [^/]
    #   .   -> \.
    parts = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*" and i + 1 < len(pattern) and pattern[i + 1] == "*":
            parts.append(".*")
            i += 2
            # Eat following / if present (a/**/b matches a/b)
            if i < len(pattern) and pattern[i] == "/":
                # Make trailing slash optional too
                parts.append("/?")
                i += 1
        elif c == "*":
            parts.append("[^/]*")
            i += 1
        elif c == "?":
            parts.append("[^/]")
            i += 1
        elif c in ".+()[]{}^$|\\":
            parts.append("\\" + c)
            i += 1
        else:
            parts.append(c)
            i += 1
    regex = "^" + "".join(parts) + "$"
    return re.match(regex, path) is not None


def _walk_python_files(repo_root: Path) -> list[str]:
    """Walk `repo_root` and return relative POSIX paths of all *.py files.

    Skips .git, __pycache__, .venv, venv, env, node_modules, .pytest_cache,
    .tox, build, dist, *.egg-info — standard noise dirs.
    """
    skip_dirs = {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        "node_modules",
        ".pytest_cache",
        ".tox",
        "build",
        "dist",
    }
    skip_dir_suffixes = (".egg-info",)
    out: list[str] = []
    for path in repo_root.rglob("*.py"):
        rel = path.relative_to(repo_root)
        parts = set(rel.parts)
        if parts & skip_dirs:
            continue
        if any(p.endswith(skip_dir_suffixes) for p in rel.parts):
            continue
        out.append(rel.as_posix())
    return sorted(out)


def run_structure_coverage(
    manifest: EngManifest, repo_root: str | Path
) -> StructureCoverageResult:
    """Run the structure-coverage check.

    Returns a result; never raises on a violation — caller decides
    whether to fail based on `--mode` (CLI handles enforce vs report).
    """
    repo_root = Path(repo_root).resolve()
    result = StructureCoverageResult()

    py_files = _walk_python_files(repo_root)
    result.files_scanned = len(py_files)

    exempt_globs = manifest.spec.exempt_paths
    deferred_globs = [(d.path, d) for d in manifest.spec.deferred_paths]
    catch_all_globs = [(b.path, b) for b in manifest.spec.catch_all_buckets]

    for rel in py_files:
        if _matches_any(rel, exempt_globs):
            result.files_exempt += 1
            continue

        # Deferred paths — explicit out-of-scope-this-pass (v0.1.1).
        # Checked AFTER exempt_paths (genuine non-subsystem files take
        # precedence) but BEFORE subsystem matching, because deferred
        # paths shouldn't be claimed by subsystems even if a glob would
        # otherwise match.
        matched_deferred = next(
            (d for path, d in deferred_globs if _matches_any(rel, [path])),
            None,
        )
        if matched_deferred:
            result.deferred[rel] = matched_deferred.path
            result.files_deferred += 1
            continue

        matched_subsystems = [
            s.id for s in manifest.spec.subsystems if _matches_any(rel, s.code_paths)
        ]

        if len(matched_subsystems) == 1:
            result.covered[rel] = matched_subsystems[0]
            result.files_covered += 1
        elif len(matched_subsystems) > 1:
            result.ambiguous[rel] = matched_subsystems
        else:
            # No subsystem claimed it. Check catch-all-under-retire
            # before flagging as a hard uncovered.
            matched_catch_all = next(
                (b for path, b in catch_all_globs if _matches_any(rel, [path])),
                None,
            )
            if matched_catch_all:
                result.catch_all_under_retire[rel] = matched_catch_all.path
            else:
                result.uncovered.append(rel)

    return result
