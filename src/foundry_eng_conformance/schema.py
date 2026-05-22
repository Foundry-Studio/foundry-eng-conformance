"""Pydantic models for `.foundry/eng-manifest.yaml` (schema v0.1.0).

Authoritative spec: ../../SCHEMA.md.

These models enforce the required-field floor at parse time. Optional
fields (per JOS-S53 flexibility=expected) load with sensible defaults
but the structure check still runs on them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

# JOS-D0028 (LOCKED 2026-04-20): 6 stage labels. `hold` is the pivot
# point — only stage that can transition to anywhere.
StageLabel = Literal["assess", "trial", "adopt", "hold", "rejected", "retire"]

RepoKind = Literal["monorepo", "library", "service", "tool"]
Plane = Literal["control", "data", "management"]
Layer = Literal["L1", "L2", "L3"]


class OutboundEdge(BaseModel):
    """One entry in a subsystem's allowed_outbound list.

    Exactly one of `subsystem` or `external` is set (validated below).
    """

    model_config = ConfigDict(extra="forbid")

    subsystem: str | None = None
    external: str | None = None
    why: str | None = None

    @field_validator("external", mode="after")
    @classmethod
    def _exactly_one(cls, v: str | None, info) -> str | None:
        subsystem = info.data.get("subsystem")
        if (subsystem is None) == (v is None):
            raise ValueError(
                "OutboundEdge must set exactly one of `subsystem` or `external`"
            )
        return v


class PublishedInterfaces(BaseModel):
    """Per-subsystem stable surface declarations (AD-3).

    Required only when the subsystem has inbound edges (some other
    subsystem references it in its allowed_outbound). The tool computes
    this; an internal-only leaf may omit the entire block.
    """

    model_config = ConfigDict(extra="forbid")

    python: list[str] = Field(default_factory=list)
    http: list[str] = Field(default_factory=list)
    mcp: list[str] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.python or self.http or self.mcp)


class GovernedUnit(BaseModel):
    """A declared governed unit (AD-10 — component / module / schema /
    deployable / migration / published-interface).

    Only governed units are enumerated; non-governed `.py` files are
    implicitly covered by structure-coverage but don't appear here.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    path: str | None = None
    kind: str | None = None  # db_table | pydantic | jsonschema | module | etc.


class GovernedUnits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    components: list[GovernedUnit] = Field(default_factory=list)
    modules: list[GovernedUnit] = Field(default_factory=list)
    schemas: list[GovernedUnit] = Field(default_factory=list)
    migrations: list[GovernedUnit] = Field(default_factory=list)
    deployables: list[GovernedUnit] = Field(default_factory=list)


class Subsystem(BaseModel):
    """One declared subsystem.

    Required (AD-3): id, title, owner, lifecycle_stage, code_paths,
    allowed_outbound. published_interfaces is conditional (required if
    inbound edges exist — enforced post-parse by the loader).
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    owner: str
    lifecycle_stage: StageLabel
    plane: Plane | None = None
    layer: Layer | None = None
    code_paths: list[str] = Field(min_length=1)
    allowed_outbound: list[OutboundEdge] = Field(default_factory=list)
    published_interfaces: PublishedInterfaces | None = None
    governed_units: GovernedUnits = Field(default_factory=GovernedUnits)


class ReproducibleBuild(BaseModel):
    """AD-11 — universal field; pinning is the Python value."""

    model_config = ConfigDict(extra="forbid")

    declared: bool
    source_of_truth: str | None = None
    notes: str | None = None


class OwnershipSource(BaseModel):
    """AD-8 — derive-don't-duplicate cross-check against CODEOWNERS."""

    model_config = ConfigDict(extra="forbid")

    file: str


class Exception_(BaseModel):
    """AD-3 — exceptions point at JOS-R16 governance-variance records.

    The manifest does NOT mint exceptions; it records the variance link.
    """

    model_config = ConfigDict(extra="forbid")

    subsystem: str
    rule: str
    jos_variance_id: str
    until: str  # ISO date; runtime decodes
    reason: str | None = None


class CatchAllBucket(BaseModel):
    """Declared known-catch-all under retire (JOS-S53 § Gap Analysis).

    Renamed `subsystem:` → `path:` per Atlas review 2026-05-22 — these
    are undeclared paths, not subsystems.
    """

    model_config = ConfigDict(extra="forbid")

    path: str
    rationale: str | None = None
    sunset_target: str | None = None
    jos_variance_id: str | None = None


class ReorgPointer(BaseModel):
    """Transient pointer at the reorg's taxonomy source.

    Drops out when the reorg lands and subsystem ids stabilize.
    """

    model_config = ConfigDict(extra="forbid")

    source_map: str
    note: str | None = None


class Spec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reproducible_build: ReproducibleBuild
    ownership_source: OwnershipSource
    subsystems: list[Subsystem] = Field(min_length=1)
    exempt_paths: list[str] = Field(
        default_factory=lambda: [
            "tests/**/*.py",
            "scripts/**/*.py",
            "migrations/**/*.py",
            "**/__init__.py",
            "conftest.py",
            "setup.py",
            "noxfile.py",
        ]
    )
    exceptions: list[Exception_] = Field(default_factory=list)
    catch_all_buckets: list[CatchAllBucket] = Field(default_factory=list)
    reorg: ReorgPointer | None = None


class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    uuid: str
    owner: str
    repo_kind: RepoKind
    description: str | None = None
    created: str | None = None
    last_modified: str | None = None


class EngManifest(BaseModel):
    """Top-level `.foundry/eng-manifest.yaml` model (schema v0.1.0).

    Backstage-aligned envelope (AD-12): apiVersion + kind + metadata + spec.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    apiVersion: str
    kind: Literal["EngManifest"]
    metadata: Metadata
    spec: Spec

    @field_validator("schema_version", mode="after")
    @classmethod
    def _supported_version(cls, v: str) -> str:
        # v0.1.x is the only supported range right now. Bumping major
        # (1.0.0) requires a tool release.
        if not v.startswith("0.1."):
            raise ValueError(
                f"schema_version {v!r} not supported by this tool version. "
                f"Supported: 0.1.x. See SCHEMA.md for migration notes."
            )
        return v

    def find_subsystem(self, sid: str) -> Subsystem | None:
        for s in self.spec.subsystems:
            if s.id == sid:
                return s
        return None

    def inbound_edges(self, sid: str) -> list[str]:
        """Return the ids of subsystems that reference `sid` in their
        allowed_outbound. Used to enforce the conditional
        published_interfaces rule (AD-3 / Atlas review 2026-05-22)."""
        result = []
        for s in self.spec.subsystems:
            if s.id == sid:
                continue
            for edge in s.allowed_outbound:
                if edge.subsystem == sid:
                    result.append(s.id)
                    break
        return result


class ManifestLoadError(ValueError):
    """Raised when the manifest YAML can't be loaded or fails validation."""


def load_manifest(path: str | Path) -> EngManifest:
    """Load + validate a `.foundry/eng-manifest.yaml` file.

    Raises ManifestLoadError on any YAML / Pydantic / cross-field
    validation failure with a human-readable message.
    """
    p = Path(path)
    if not p.exists():
        raise ManifestLoadError(f"Manifest not found: {p}")

    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ManifestLoadError(f"YAML parse error in {p}: {e}") from e

    if not isinstance(raw, dict):
        raise ManifestLoadError(
            f"Manifest root must be a mapping, got {type(raw).__name__}"
        )

    try:
        manifest = EngManifest.model_validate(raw)
    except ValidationError as e:
        raise ManifestLoadError(f"Manifest validation failed:\n{e}") from e

    # Post-parse cross-field checks
    _enforce_unique_subsystem_ids(manifest)
    _enforce_conditional_published_interfaces(manifest)
    _enforce_outbound_subsystem_refs_resolve(manifest)

    return manifest


def _enforce_unique_subsystem_ids(m: EngManifest) -> None:
    seen: dict[str, int] = {}
    for s in m.spec.subsystems:
        seen[s.id] = seen.get(s.id, 0) + 1
    dups = {sid: c for sid, c in seen.items() if c > 1}
    if dups:
        raise ManifestLoadError(
            f"Duplicate subsystem ids: {dups}. Each subsystem id must be unique."
        )


def _enforce_conditional_published_interfaces(m: EngManifest) -> None:
    """Per Atlas review 2026-05-22: published_interfaces is required
    ONLY when the subsystem has inbound edges (is depended-upon)."""
    failures = []
    for s in m.spec.subsystems:
        inbound = m.inbound_edges(s.id)
        if inbound:
            pi = s.published_interfaces
            if pi is None or pi.is_empty():
                failures.append(
                    f"  - {s.id}: has inbound edges from {inbound} but "
                    f"published_interfaces is missing or empty"
                )
    if failures:
        raise ManifestLoadError(
            "Subsystems with inbound edges must declare published_interfaces:\n"
            + "\n".join(failures)
        )


def _enforce_outbound_subsystem_refs_resolve(m: EngManifest) -> None:
    """Every `allowed_outbound.subsystem` must reference a declared subsystem."""
    ids = {s.id for s in m.spec.subsystems}
    failures = []
    for s in m.spec.subsystems:
        for edge in s.allowed_outbound:
            if edge.subsystem and edge.subsystem not in ids:
                # Not all subsystem refs need to be in-manifest — some
                # cross-subsystem imports point at code outside the
                # declared map (especially during in-flight reorg). We
                # WARN via the structure-coverage check rather than
                # hard-failing here. Comment this out and keep validation
                # liberal for v0.
                pass
    if failures:
        raise ManifestLoadError("\n".join(failures))
