# foundry-eng-conformance

Foundry-Studio's shared eng-conformance tool. Implements the checks
[JOS-S53 (Architecture Conformance Standard)](https://github.com/Foundry-Studio/jordan-operating-system/blob/main/standards/JOS-S53-architecture-conformance-standard.md)
requires:

1. **Structure coverage** — every code unit maps to exactly one declared
   subsystem. No code lives in an undeclared catch-all bucket.
2. **Dependency direction + acyclic** — the actual import graph respects
   the declared allowed edges, and there are no cycles (JOS-P20).

The tool reads a per-repo manifest at **`.foundry/eng-manifest.yaml`**
(see [SCHEMA.md](SCHEMA.md) for the manifest contract).

## Status

Alpha. v0.1.0. The schema and the tool ship together — both versioned.

The schema (`schema_version: 0.1.0`) is the **shared contract** between
this tool and the in-flight FAS `src/` reorg. Both consume it. Don't fork it.

## Install

Standard pip install from a git tag/SHA (foundry-cip style, per D-152):

```bash
pip install "foundry-eng-conformance @ git+https://github.com/Foundry-Studio/foundry-eng-conformance@v0.1.0"
```

Or by SHA for reproducibility:

```bash
pip install "foundry-eng-conformance @ git+https://github.com/Foundry-Studio/foundry-eng-conformance@<sha>"
```

Local dev:

```bash
git clone https://github.com/Foundry-Studio/foundry-eng-conformance.git
cd foundry-eng-conformance
pip install -e ".[dev]"
pytest
```

## Quick start

1. Drop a manifest at `.foundry/eng-manifest.yaml` in your repo
   (see [`examples/eng-manifest.example.yaml`](examples/eng-manifest.example.yaml)
   for a starting shape).

2. Run the checks:

   ```bash
   foundry-eng-conformance check
   ```

3. Wire into CI:

   ```yaml
   # .github/workflows/conformance.yml
   - run: pip install "foundry-eng-conformance @ git+https://github.com/Foundry-Studio/foundry-eng-conformance@v0.1.0"
   - run: foundry-eng-conformance check --mode=report  # advisory window
   ```

   Switch `--mode=report` → `--mode=enforce` once your violation
   count stabilizes at zero.

## Mode flag (advisory window vs. enforce)

Per the Atlas review pattern (2026-05-22), conformance pilots open in
**report mode** first:

| Mode           | Behavior                                                                |
|----------------|-------------------------------------------------------------------------|
| `--mode=report`  *(default)* | Emit evidence + print violation counts. **Always exits 0.** Use during in-flight reorgs and the initial pilot window. |
| `--mode=enforce`             | Emit evidence + print violation counts. **Exits non-zero on any check fail or missing required check.** Use after the violation count is stable at zero. |

This is the AD-8 "advisory window before enforce" discipline — a
blocking gate during an in-flight reorg deadlocks the reorg or gets
bypassed.

## What gets emitted

Every check run appends evidence to
`evidence/YYYY-MM-DD/eng-conformance.jsonl` (per AD-2 + JOS-D0063
append-only evidence ledger). Each record:

```json
{
  "check_id": "structure-coverage",
  "category": "structure",
  "tool": "foundry-eng-conformance@0.1.0",
  "result": "pass",
  "commit_sha": "abc1234...",
  "evidence_uri": "evidence/2026-05-22/eng-conformance.jsonl#L1",
  "timestamp": "2026-05-22T14:00:00Z",
  "details": { "files_scanned": 1024, "files_covered": 1020, ... }
}
```

The gate in `--mode=enforce` verifies that one record exists per
required check and that none of them are `result: "fail"`.

## The two checks

### 1. Structure coverage (our own logic)

Walks the repo tree under each declared `code_paths` glob:

- **PASS** — file matches exactly one subsystem.
- **SKIP** — file matches `spec.exempt_paths` (tests, scripts, __init__.py, etc.).
- **UNCOVERED** — file matches zero subsystems → catch-all violation.
- **AMBIGUOUS** — file matches two or more subsystems → declaration overlap.

`spec.catch_all_buckets` carves out declared known-catch-alls under retire —
these are reported separately (not as a hard violation), with a sunset
target tracked.

### 2. Dependency direction + acyclic (import-linter backend)

For each subsystem, compiles the manifest's `allowed_outbound` into
[import-linter](https://github.com/seddonym/import-linter) contracts and
walks the actual import graph (via grimp). Reports:

- **disallowed_outbound** — a file in subsystem A imports from
  subsystem B, but B is not in A's `allowed_outbound`.
- **cycle** — a pair of subsystems with import paths in both
  directions (violates JOS-P20).

import-linter handles the heavy lifting (graph construction, cycle
detection). The manifest-to-contract translation is our adapter.

## Subcommands

```text
foundry-eng-conformance check     Run all conformance checks
foundry-eng-conformance validate  Validate manifest syntax + cross-field rules
foundry-eng-conformance --help    Show help
```

## Roadmap

- **v0.1.x** — initial alpha; FAS monorepo as the first pilot
- **v0.2.x** — universal vs Python-stack-pack split (AD-9 firewall),
  gated on the CIP shape-check
- **v1.0.x** — schema stable; second-shape (CIP) onboarded

## Governance

- Implements [JOS-S53](https://github.com/Foundry-Studio/jordan-operating-system/blob/main/standards/JOS-S53-architecture-conformance-standard.md) (stage_label=assess)
- Pinned at [SCHEMA.md](SCHEMA.md) v0.1.0
- Owner: tim
- License: Apache 2.0
