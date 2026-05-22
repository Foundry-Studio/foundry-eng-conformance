---
doc_type: manifest-schema-spec
workstream: JOS Engineering Domain (JOS-ENG) — Part B
status: v0-approved-build-go
owner: tim
authorship: claude-code-drafted
created: 2026-05-22
last_modified: 2026-05-22
revisions:
  - 2026-05-22 v0 first draft — Part B first deliverable
  - 2026-05-22 v0.1 approved with 4 fold-ins (Atlas review):
      mode flag (--mode=report|enforce); exempt_paths promoted to v0;
      lifecycle_stage enum aligned to JOS-D0028 (assess/trial/adopt/
      hold/rejected/retire); catch_all_buckets renamed to use path:
      not subsystem:; published_interfaces required only when
      depended-upon.
purpose: >
  The shared contract between the FAS src/ reorg and the
  foundry-eng-conformance tool. Both consume this schema; if they
  define it independently they diverge and one gets redone. Per
  Tim's directive 2026-05-22: schema is Part B's first deliverable,
  formalized here before the tool is implemented or the reorg
  produces its declared map.
related:
  - WORKBENCH/tim/jos-eng-domain/PANEL-SYNTHESIS-AND-DECISIONS-2026-05-22.md (AD-1..AD-12)
  - WORKBENCH/tim/jos-eng-domain/CC-HANDOFF-2026-05-22.md (Part B spec)
  - WORKBENCH/tim/library-build/TARGET-STATE-MAP.md (subsystem taxonomy this targets)
  - WORKBENCH/tim/library-build/LIB-ENG-CONFORMANCE-CONTRIBUTIONS.md (strawman shape this formalizes)
  - jordan-operating-system/standards/JOS-S53-architecture-conformance-standard.md (the standard this implements)
  - jordan-operating-system/decisions/JOS-D0049-universal-base-manifest.md (universal base manifest this extends)
---

# Eng Manifest Schema — v0

> **Status:** proposal. Locks when (a) the FAS reorg session sees this
> and either uses it or surfaces a concrete change; (b) the tool's
> first implementation lands in `Foundry-Studio/foundry-eng-conformance`
> and the schema doc migrates there as authoritative.

## What this is

A single declarative file — **`.foundry/eng-manifest.yaml`** — that
declares, per repo, how the code is organized into the architectural
components and boundaries of the system's stated architecture, plus the
governance metadata (owner, lifecycle, exceptions) that JOS-S53
requires.

The schema is what the `foundry-eng-conformance` tool consumes to run
JOS-S53's checks: **structure coverage** (every code unit maps to a
declared component; no catch-all bucket) + **dependency direction**
(actual import graph respects declared allowed edges + acyclic per
JOS-P20).

## What this is NOT

- Not a Backstage `catalog-info.yaml`. The entity-model *fields* align
  with Backstage (per AD-12 — interop, not dependency), but the file
  is foundry-owned and lives in the repo, not in a Backstage IDP.
- Not a replacement for `pyproject.toml` / `CODEOWNERS` / lockfiles.
  Those remain canonical for their domains; this manifest is the
  declared-architecture layer that sits above them (and cross-checks
  against them per AD-8).
- Not a place to declare every file. Per AD-10, only **governed units**
  (component, module, schema, deployable, migration,
  published-interface) are enumerated.

## File location

```
<repo-root>/.foundry/eng-manifest.yaml
```

Rationale (per Tim's coordination call 2026-05-22):

- Out of `.jos/`: that namespace belongs to JOS doctrine. The manifest
  is venture self-description read by a Foundry-Studio tool, not JOS.
- Separate file, not a block inside the JOS charter: avoids bumping
  the charter schema (1.9 → 1.10), which would force a re-sync across
  all 13 governed charters.
- Under `.foundry/`: namespaces under a Foundry-Studio-tooling root,
  leaving room for future siblings (e.g.
  `.foundry/release-manifest.yaml` for AD-5).

## Top-level shape

```yaml
# .foundry/eng-manifest.yaml
schema_version: "0.1.0"
apiVersion: foundry.studio/v1     # Backstage-aligned (AD-12)
kind: EngManifest

metadata:
  name: foundry-agent-system        # repo identifier
  uuid: "f7a3b2e1-..."              # JOS universal base manifest field (D-049)
  owner: tim                        # AD-3 required
  repo_kind: monorepo               # monorepo | library | service | tool — drives required-ness (AD-5)
  description: "Foundry's agent + work-execution monorepo"
  created: "2026-05-22"
  last_modified: "2026-05-22"

spec:
  # ── Reproducibility (AD-11) ─────────────────────────────────────
  reproducible_build:
    declared: true
    source_of_truth: pyproject.toml   # or "requirements.txt+lockfile" etc.
    notes: "uv-compiled per FND-S13"

  # ── Ownership source (AD-3 + AD-8 derive-don't-duplicate) ──────
  ownership_source:
    file: CODEOWNERS                  # or ".github/CODEOWNERS"
    # Tool cross-checks per-subsystem owners against this file.

  # ── Structure-coverage exemptions (fold-in 2026-05-22 review) ──
  # Files matching ANY of these globs are exempt from structure-coverage.
  # Seeded with the obvious defaults; pilot will surface more (top-level
  # __init__.py, app entrypoints, config modules typically end up here).
  # Per Atlas review: implement now rather than defer — needed almost
  # immediately at pilot time.
  exempt_paths:
    - "tests/**/*.py"
    - "scripts/**/*.py"
    - "migrations/**/*.py"
    - "**/__init__.py"          # package markers (usually no code; pilot may narrow)
    - "conftest.py"             # pytest collection
    - "setup.py"                # legacy install
    - "noxfile.py"              # task runner
    # Add repo-specific entries as pilot surfaces them (e.g. main.py,
    # alembic env.py, vendor/).

  # ── Subsystem declarations (the structural map) ────────────────
  # lifecycle_stage MUST be one of (JOS-D0028, 2026-04-20 LOCKED):
  #   assess | trial | adopt | hold | rejected | retire
  # `hold` is the pivot point — only stage that can transition anywhere.
  subsystems:
    - id: "work-definition/definitions"   # canonical id; matches TARGET-STATE-MAP taxonomy
      title: "Work Definition — Definitions subsystem"
      owner: tim                          # AD-3 required (cross-checks against ownership_source)
      lifecycle_stage: adopt              # JOS-D0028 enum (see above)
      plane: control                      # Control | Data | Management (from TARGET-STATE-MAP)
      layer: L1                           # L1 Intent | L2 Substrate | L3 Effectors (from TARGET-STATE-MAP)

      code_paths:
        - "src/work_definition/definitions/**/*.py"
        # Globs are evaluated relative to repo root. Each .py file MUST match
        # exactly one subsystem's code_paths (structure-coverage check),
        # unless it matches `spec.exempt_paths` above.

      allowed_outbound:
        # What this subsystem MAY depend on (Python import targets).
        # Two kinds of entries:
        # (a) "<subsystem-id>"      — other declared subsystems
        # (b) "<python-module>"      — external packages / stdlib
        - subsystem: "system_integrity.contracts"
          why: "ComponentEnvelope subclass; validate_component"
        - subsystem: "utils"
          why: "canonicalize_json (D-005 content-hash)"
        - subsystem: "db"
          why: "SQLAlchemy ORM"
        - subsystem: "api.dependencies"
          why: "get_identity helper (A14)"
        - external: "sqlalchemy"
        - external: "pydantic"
        - external: "jsonschema"

      published_interfaces:                # AD-3 — required only if subsystem has inbound edges
        # What other code MAY consume from this subsystem. Stable surface.
        # Per Atlas review (2026-05-22): required ONLY for subsystems that
        # are imported by other subsystems (have inbound edges). Internal-only
        # leaves can omit the block to avoid boilerplate empties.
        # The tool detects inbound edges from other subsystems'
        # `allowed_outbound.subsystem` references — if any other subsystem
        # references this one, this block MUST exist and be non-empty.
        python:
          - "work_definition.definitions.library_service"
          - "work_definition.definitions.instantiation_service"
          - "work_definition.definitions.proposal_service"
          - "work_definition.definitions.library_lookup_service"
          - "work_definition.definitions.master_validator"
        http:
          - "POST /api/v1/pm/library/items/{item_id}/bless"
          - "GET  /api/v1/pm/library/inbox"
        mcp:
          - "foundry_mcp_lib_lookup"
          - "foundry_mcp_lib_instantiate"
          - "foundry_mcp_lib_propose"
          - "foundry_mcp_lib_record_eval"

      governed_units:                      # AD-10 — declared, not auto-discovered
        # Only governed units get enumerated. Other code in code_paths is
        # implicitly covered by the structure-coverage check (every .py file
        # maps to this subsystem) but doesn't need per-file declaration.
        components:                         # DB tables, contracts, etc.
          - id: "library_items"
            kind: db_table
          - id: "library_item_versions"
            kind: db_table
          - id: "library_item_tags"
            kind: db_table
        modules:                            # Python service modules with stable callable surfaces
          - id: "library_service"
            path: "src/work_definition/definitions/library_service.py"
          - id: "instantiation_service"
            path: "src/work_definition/definitions/instantiation_service.py"
        schemas:                            # Pydantic contracts, JSON schemas
          - id: "LibraryItemRegistration"
            kind: pydantic
            path: "src/system_integrity/contracts/library_item_contract.py"
        migrations:                         # Alembic migrations
          - id: "lib_d5_substrate"
            path: "migrations/versions/2026_*_lib_d5_substrate.py"
        deployables: []                     # Things that ship somewhere (containers, lambdas, pip packages)

    - id: "work-execution/task_queue"
      title: "Work Execution — Task Queue"
      owner: tim
      lifecycle_stage: adopt
      plane: data
      layer: L2
      code_paths:
        - "src/work_execution/task_queue/**/*.py"
      allowed_outbound:
        - subsystem: "db"
        - subsystem: "work-definition/containers"
          why: "Read scope/task definitions to dispatch"
        - external: "psycopg"
      published_interfaces:
        python:
          - "work_execution.task_queue.dispatcher"
      governed_units:
        modules:
          - id: "dispatcher"
            path: "src/work_execution/task_queue/dispatcher.py"

  # ── Exceptions (AD-3: route through JOS-R16, recorded here for visibility) ──
  exceptions:
    # Each exception MUST point at a JOS-R16 governance-variance record.
    # The manifest does NOT mint exceptions — it just records the variance link.
    - subsystem: "work-definition/definitions"
      rule: "allowed_outbound.no_engines"
      jos_variance_id: "JOS-VAR-2026-05-25-001"
      until: "2026-08-01"
      reason: "Temporary engine import during reorg D-180 migration"

  # ── Catch-all detection (structure-coverage half) ──────────────
  # OPTIONAL: declared known-catch-alls under retire (JOS-S53 § Gap Analysis
  # Guide). The tool reports any file under these paths as a "catch-all
  # under retire" finding, distinct from an "undeclared" finding. Each entry
  # SHOULD have a sunset_target date and ideally a JOS-R16 variance link.
  # Renamed from `subsystem:` to `path:` per Atlas review 2026-05-22 — these
  # are undeclared paths, not subsystems.
  catch_all_buckets:
    - path: "src/services/**/*.py"
      rationale: "Legacy services/ dir under retire; reorg D-180 splits across subsystems"
      sunset_target: "2026-09-01"
      jos_variance_id: null               # optional — point at JOS-R16 record if one exists

  # ── Reorg pointer (transient, drops out when reorg is done) ────
  reorg:
    source_map: "WORKBENCH/tim/library-build/TARGET-STATE-MAP.md"
    note: "Subsystem ids match the TARGET-STATE-MAP taxonomy. When the
           reorg completes and the taxonomy stabilizes, this pointer is
           removed."
```

## Evidence contract (AD-2)

Separate artifact, not part of the manifest. Emitted by the tool on every
check run, appended to `evidence/YYYY-MM-DD/eng-conformance.jsonl` per
JOS-D0063 conventions:

```jsonl
{"check_id": "structure-coverage", "category": "structure", "tool": "foundry-eng-conformance@0.1.0", "result": "pass", "commit_sha": "179b9db...", "evidence_uri": "evidence/2026-05-22/eng-conformance.jsonl#L42", "timestamp": "2026-05-22T14:00:00Z", "details": {"files_checked": 1024, "files_uncovered": 0}}
{"check_id": "dependency-direction", "category": "structure", "tool": "foundry-eng-conformance@0.1.0", "result": "fail", "commit_sha": "179b9db...", "evidence_uri": "evidence/2026-05-22/eng-conformance.jsonl#L43", "timestamp": "2026-05-22T14:00:00Z", "details": {"violation_count": 2, "violations": [{"from": "work-definition/definitions", "to": "agents.team", "reason": "disallowed-outbound"}]}}
{"check_id": "acyclic", "category": "structure", "tool": "foundry-eng-conformance@0.1.0", "result": "pass", "commit_sha": "179b9db...", "evidence_uri": "evidence/2026-05-22/eng-conformance.jsonl#L44", "timestamp": "2026-05-22T14:00:00Z", "details": {"cycle_count": 0}}
```

Gate behavior (CI) — depends on `--mode` flag:

**`--mode=report` (default for the FAS pilot, AD-8 advisory window)**:

- Emit evidence record(s) as normal.
- Print violation counts to stdout.
- **Exit 0 regardless of result** — does not fail CI.
- Use case: in-flight reorg where many `.py` files are transiently
  uncovered or misplaced. A blocking gate here would deadlock the reorg
  or get bypassed. Report mode lets the violation count trend to zero
  visibly as the reorg lands; flip to `enforce` only when the trend is
  stable at zero.

**`--mode=enforce`** (post-pilot, blocking gate):

- Reads `evidence/<today>/eng-conformance.jsonl` (or the latest by
  `commit_sha`).
- Verifies one record exists per `required_check_ids` (drawn from
  schema_version's required set).
- `result: "fail"` on any required check → CI exit non-zero.
- Missing required check record → CI exit non-zero (this is the
  AD-2 fix: "verify evidence exists for required checks," not "did
  CI run").

Rollout discipline per Atlas review 2026-05-22:

1. FAS pilot opens in `--mode=report`.
2. Reorg lands; violation count tracked over time as a single number.
3. When count holds at zero across N consecutive runs (TBD — propose 5
   green CI runs), flip the FAS CI invocation to `--mode=enforce`.
4. CIP onboards in `--mode=report` first, same discipline.

## The two checks (Python first stack pack)

### 1. Structure coverage (our own logic — see Tim's split)

Walk the repo tree under each declared `code_paths` glob. For every
`*.py` file in the repo:

- Match the file's path against every subsystem's `code_paths` globs.
- **PASS**: file matches exactly one subsystem.
- **FAIL (uncovered)**: file matches zero subsystems → catch-all violation.
- **FAIL (ambiguous)**: file matches two+ subsystems → declaration overlap.

Exempt by default:
- `tests/**/*.py` (handled separately by test-conformance, not Ring 1)
- `scripts/**/*.py` (operational, declared in a future scripts subsystem
  or exempted via JOS-R16)
- `migrations/**/*.py` (covered by per-subsystem `governed_units.migrations`)

Exemptions live in `.foundry/eng-manifest.yaml` under a top-level
`exempt_paths:` field (TBD if needed — start without it, add if FAS
pilot demands).

### 2. Dependency direction + acyclic (import-linter backend, our manifest)

For each subsystem in the manifest:

- Compile the subsystem's `allowed_outbound` into import-linter contracts:
  - `Contract: forbid_imports` — forbids any module path NOT in
    `allowed_outbound` from being imported by code under
    `code_paths`.
  - `Contract: layered` — declares planes (Control / Data / Management)
    as layers; enforces no upward dependency.
- Run import-linter against the resulting `.importlinter` config (compiled
  in-memory or to a temp file, not committed).
- Add a separate acyclic check (import-linter's `independence` /
  `forbidden` contracts) per JOS-P20.

The translation `manifest → import-linter contracts` is our adapter
code. import-linter handles the dep-graph walking and cycle detection.

## Schema-version + evolution policy

- `schema_version: "0.1.0"` for this v0. Breaking changes bump major
  (0.x.0 → 1.0.0).
- The tool ships pinned to a manifest range (e.g. `0.x.y`); manifests
  declare their `schema_version`; tool errors out with a clear migration
  message on mismatch.
- Per AD-12, schema evolution targets Backstage compatibility at the
  entity-model level. Foundry-specific extensions live under `spec.*`
  not `metadata.*`.

## Required fields (the floor — schema_version 0.1.0)

Per JOS-S53 + AD-1 minimum outcomes + AD-3:

For the manifest:
- `schema_version`, `apiVersion`, `kind`
- `metadata.name`, `metadata.uuid`, `metadata.owner`, `metadata.repo_kind`
- `spec.subsystems` (non-empty)
- `spec.reproducible_build.declared`
- `spec.ownership_source.file`

For each subsystem:
- `id`, `title`, `owner`, `lifecycle_stage`, `code_paths`,
  `allowed_outbound`, `published_interfaces`

Optional but expected (flexibility=expected per JOS-S53 itself):
- `plane`, `layer` (richness for TARGET-STATE-MAP alignment)
- `governed_units.*` (AD-10 unit enumeration)
- `exceptions` (only when active)

## Auto-derivation strategy (AD-8)

`foundry-eng-conformance init` bootstraps `.foundry/eng-manifest.yaml`
by:

1. Walking the repo tree, grouping `src/**/<dir>/` as candidate
   subsystem ids.
2. Reading `CODEOWNERS` to seed `owner` per subsystem.
3. Reading `pyproject.toml` (any `[tool.foundry.subsystems.*]` blocks
   from LIB-style strawmen) to seed `allowed_outbound` /
   `published_interfaces.python`.
4. Producing a manifest stub with `# TODO` markers for anything it
   couldn't derive.

After bootstrap, the manifest is canonical. The other files
(`CODEOWNERS`, `pyproject.toml`) remain canonical for their domains and
are cross-checked, not duplicated. AD-8's "don't hand-author" applies to
starting from a blank file — editing the bootstrapped manifest by hand
to declare deps / interfaces is normal.

## Backstage compatibility (AD-12)

The `metadata` fields are a strict subset of Backstage's `catalog-info.yaml`
entity model:

| Backstage field      | EngManifest field          | Notes                                  |
|----------------------|----------------------------|----------------------------------------|
| `apiVersion`         | `apiVersion`               | Foundry namespace, not backstage.io    |
| `kind`               | `kind`                     | "EngManifest" instead of "System"      |
| `metadata.name`      | `metadata.name`            | Identical                              |
| `metadata.owner`     | `metadata.owner`           | Identical                              |
| `metadata.description` | `metadata.description`   | Identical                              |
| `spec.type`          | `metadata.repo_kind`       | Mapped during interop                  |
| `spec.lifecycle`     | `subsystems[*].lifecycle_stage` | Per-subsystem rather than per-repo |

A future `foundry-to-backstage` adapter is a ~50 LOC YAML rewriter.
**Not** a v1 deliverable.

## Open questions deferred to v0.2

- **AD-9 firewall — universal vs Python-stack-pack split [GATED ON CIP].**
  This v0 mixes universal fields (owner, lifecycle, exceptions) with
  Python-specifics (`published_interfaces.python`,
  `allowed_outbound.external` as Python module names). Per AD-9, these
  should eventually be in two layers: universal + stack pack. **Per
  Atlas review 2026-05-22**: do NOT declare the schema "stable" or
  onboard CIP until the universal-vs-stack-pack split decision is made.
  CIP is the second shape that tests it — the CIP shape-check IS the
  AD-9 test. The split decision surfaces at that point, not before.
  The current `python:` / `external:` nesting under `published_interfaces`
  and `allowed_outbound` already does most of the structural separation
  the split will formalize.
- **Layered-architecture contract direction.** TARGET-STATE-MAP defines
  three planes (Control / Data / Management). v0 records `plane` per
  subsystem but doesn't yet declare which planes can import from
  which. v0.2 should add a top-level `spec.plane_rules:` block.
- **Exempt_paths for tests / scripts.** Not in v0; added if FAS pilot
  surfaces specific files that must be exempted from structure-coverage.
- **JOS-R16 variance integration.** v0 lists `jos_variance_id` strings
  but the tool doesn't yet round-trip with the JOS variance system.
  When JOS variances become first-class queryable, the tool can verify
  the cited variance exists and hasn't expired.

## Coordination contract (the reason this doc exists)

**For the FAS src/ reorg session**: when you declare your subsystem
taxonomy + dependency directions, produce them *in this schema*. If
the schema's missing a field you need, edit this doc (it's still v0,
not locked) and surface the change. Don't invent a parallel format —
that's exactly the divergence Tim's coordination flag warned about.

**For the foundry-eng-conformance build (next session)**: the schema
is the spec. The tool's repo (when bootstrapped) gets this doc copied
in as `SCHEMA.md` v0.1.0. The implementation reads `.foundry/eng-manifest.yaml`
against this schema; tests cover the schema's required fields and the
two checks (structure-coverage + dependency-direction).

## Change Log

| Date       | Change                              | Author |
|------------|-------------------------------------|--------|
| 2026-05-22 | v0 proposal — Part B first deliverable | claude |
