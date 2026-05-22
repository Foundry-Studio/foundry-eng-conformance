"""Command-line interface for `foundry-eng-conformance`.

Subcommands:
    check    Run all conformance checks against a repo's manifest.
    validate Validate manifest syntax + cross-field rules; don't walk
             the code tree or build the import graph.

The `check` mode flag (`--mode=report|enforce`) controls CI exit codes
per Atlas review 2026-05-22:

    --mode=report   (default — for the FAS pilot's advisory window)
        Emit evidence, print violation counts, ALWAYS exit 0.

    --mode=enforce  (post-pilot, blocking gate)
        Emit evidence, print violation counts, exit non-zero on any
        check `result: "fail"` OR missing required check record.

Exit codes:
    0  PASS (or report mode regardless of result)
    1  FAIL (enforce mode, one or more checks reported fail)
    2  Configuration error (missing manifest, schema mismatch, etc.)
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from foundry_eng_conformance import __schema_version__, __version__
from foundry_eng_conformance.checks.dependency_direction import (
    run_dependency_direction,
)
from foundry_eng_conformance.checks.structure_coverage import (
    run_structure_coverage,
)
from foundry_eng_conformance.evidence import EvidenceRecord, emit_records
from foundry_eng_conformance.reporters import (
    format_dependency_direction,
    format_structure_coverage,
)
from foundry_eng_conformance.schema import (
    ManifestLoadError,
    load_manifest,
)


def _find_manifest(repo_root: Path) -> Path:
    """Default manifest location: <repo>/.foundry/eng-manifest.yaml."""
    return repo_root / ".foundry" / "eng-manifest.yaml"


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=__version__, prog_name="foundry-eng-conformance")
def main() -> None:
    """Foundry-Studio eng-conformance — JOS-S53 checks against a repo's manifest."""


@main.command()
@click.option(
    "--repo",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path.cwd(),
    help="Path to the repo root. Defaults to the current working directory.",
)
@click.option(
    "--manifest",
    type=click.Path(path_type=Path),
    default=None,
    help="Explicit manifest path. Defaults to <repo>/.foundry/eng-manifest.yaml.",
)
@click.option(
    "--mode",
    type=click.Choice(["report", "enforce"], case_sensitive=False),
    default="report",
    help=(
        "report (default): emit evidence + print, ALWAYS exit 0. "
        "enforce: exit non-zero on any check fail or missing required check."
    ),
)
@click.option(
    "--no-emit-evidence",
    is_flag=True,
    default=False,
    help="Skip writing evidence/YYYY-MM-DD/eng-conformance.jsonl (dry-run).",
)
def check(repo: Path, manifest: Path | None, mode: str, no_emit_evidence: bool) -> None:
    """Run all conformance checks (structure-coverage + dependency-direction)."""
    repo_root = repo.resolve()
    manifest_path = manifest or _find_manifest(repo_root)
    if not manifest_path.exists():
        click.secho(
            f"ERROR: manifest not found at {manifest_path}\n"
            f"  Hint: foundry-eng-conformance reads "
            f"<repo>/.foundry/eng-manifest.yaml by default.\n"
            f"  See SCHEMA.md in the foundry-eng-conformance repo for the "
            f"manifest contract.",
            fg="red",
            err=True,
        )
        sys.exit(2)

    try:
        m = load_manifest(manifest_path)
    except ManifestLoadError as e:
        click.secho(f"ERROR: {e}", fg="red", err=True)
        sys.exit(2)

    click.echo(
        f"foundry-eng-conformance@{__version__} "
        f"(schema {__schema_version__}, mode={mode})"
    )
    click.echo(f"  Repo:     {repo_root}")
    click.echo(f"  Manifest: {manifest_path.relative_to(repo_root) if manifest_path.is_relative_to(repo_root) else manifest_path}")
    click.echo(f"  Subsystems declared: {len(m.spec.subsystems)}")
    click.echo("")

    # ── Run the two checks ──
    structure_res = run_structure_coverage(m, repo_root)
    click.echo(format_structure_coverage(structure_res))
    click.echo("")

    dep_res = run_dependency_direction(m, repo_root)
    click.echo(format_dependency_direction(dep_res))
    click.echo("")

    # ── Build evidence records (AD-2) ──
    def result_str(passed: bool, skipped: str | None) -> str:
        if skipped:
            return "skipped"
        return "pass" if passed else "fail"

    records = [
        EvidenceRecord(
            check_id="structure-coverage",
            result=result_str(structure_res.passed, None),
            details=structure_res.to_details(),
        ),
        EvidenceRecord(
            check_id="dependency-direction",
            result=result_str(dep_res.passed, dep_res.skipped_reason),
            details=dep_res.to_details(),
        ),
    ]

    if not no_emit_evidence:
        out_path = emit_records(records, repo_root)
        click.echo(f"Evidence written: {out_path.relative_to(repo_root)}")
    else:
        click.echo("Evidence emission skipped (--no-emit-evidence)")

    # ── Decide exit code ──
    any_fail = any(r.result == "fail" for r in records)
    if mode == "enforce" and any_fail:
        click.secho(
            "FAIL: one or more checks reported violations (mode=enforce)",
            fg="red",
        )
        sys.exit(1)
    if mode == "report" and any_fail:
        click.secho(
            "Report mode: violations present, but exit 0 per --mode=report. "
            "Flip to --mode=enforce once violation count stabilizes at zero.",
            fg="yellow",
        )
    else:
        click.secho("All checks passed.", fg="green")
    sys.exit(0)


@main.command()
@click.option(
    "--repo",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path.cwd(),
)
@click.option(
    "--manifest",
    type=click.Path(path_type=Path),
    default=None,
)
def validate(repo: Path, manifest: Path | None) -> None:
    """Validate manifest syntax + cross-field rules. Does not walk code."""
    repo_root = repo.resolve()
    manifest_path = manifest or _find_manifest(repo_root)
    if not manifest_path.exists():
        click.secho(f"ERROR: manifest not found at {manifest_path}", fg="red", err=True)
        sys.exit(2)
    try:
        m = load_manifest(manifest_path)
    except ManifestLoadError as e:
        click.secho(f"ERROR: {e}", fg="red", err=True)
        sys.exit(2)
    click.secho(
        f"Manifest OK — schema {m.schema_version}, "
        f"{len(m.spec.subsystems)} subsystem(s) declared.",
        fg="green",
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
