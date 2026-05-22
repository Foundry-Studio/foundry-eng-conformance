"""Tests for src/foundry_eng_conformance/schema.py."""

from __future__ import annotations

import pytest

from foundry_eng_conformance.schema import (
    EngManifest,
    ManifestLoadError,
    load_manifest,
)


class TestHappyPath:
    def test_minimal_loads(self, write_manifest):
        path = write_manifest()
        m = load_manifest(path)
        assert isinstance(m, EngManifest)
        assert m.schema_version == "0.1.0"
        assert m.kind == "EngManifest"
        assert len(m.spec.subsystems) == 2

    def test_default_exempt_paths_seeded(self, write_manifest):
        path = write_manifest()
        m = load_manifest(path)
        assert "tests/**/*.py" in m.spec.exempt_paths
        assert "migrations/**/*.py" in m.spec.exempt_paths
        assert "**/__init__.py" in m.spec.exempt_paths

    def test_inbound_edges_computed(self, write_manifest):
        path = write_manifest()
        m = load_manifest(path)
        # beta depends on alpha → alpha has inbound from beta
        assert m.inbound_edges("alpha") == ["beta"]
        assert m.inbound_edges("beta") == []


class TestStageLabelEnum:
    """JOS-D0028 — only 6 stage labels are valid."""

    @pytest.mark.parametrize(
        "stage", ["assess", "trial", "adopt", "hold", "rejected", "retire"]
    )
    def test_valid_stages_accepted(self, write_manifest, stage):
        path = write_manifest(
            {"spec": {"subsystems": [
                {
                    "id": "alpha",
                    "title": "Alpha",
                    "owner": "tim",
                    "lifecycle_stage": stage,
                    "code_paths": ["src/alpha/**/*.py"],
                    "published_interfaces": {"python": ["alpha.x"]},
                },
                {
                    "id": "beta",
                    "title": "Beta",
                    "owner": "tim",
                    "lifecycle_stage": stage,
                    "code_paths": ["src/beta/**/*.py"],
                    "allowed_outbound": [{"subsystem": "alpha"}],
                },
            ]}}
        )
        m = load_manifest(path)
        assert m.spec.subsystems[0].lifecycle_stage == stage

    def test_invalid_stage_rejected(self, write_manifest):
        with pytest.raises(ManifestLoadError):
            path = write_manifest(
                {"spec": {"subsystems": [
                    {
                        "id": "alpha",
                        "title": "Alpha",
                        "owner": "tim",
                        "lifecycle_stage": "pilot",  # not in JOS-D0028 enum
                        "code_paths": ["src/alpha/**/*.py"],
                    },
                ]}}
            )
            load_manifest(path)


class TestRequiredFields:
    def test_missing_owner_rejected(self, write_manifest, minimal_manifest_dict):
        # Build a manifest dict with owner explicitly removed from metadata.
        # The write_manifest fixture deep-merges, so we mutate the underlying
        # dict directly here to avoid the merge re-adding owner.
        import yaml as _yaml
        from pathlib import Path as _Path

        del minimal_manifest_dict["metadata"]["owner"]
        # write_manifest fixture writes its frozen minimal dict, so do it
        # manually for this case.
        path = _Path(write_manifest.__self__.tmp_path if hasattr(write_manifest, '__self__') else "")
        # Simpler: write a fresh manifest file ourselves
        import tempfile, os
        # Use the existing target path the fixture uses
        target = write_manifest()  # creates default manifest
        target.write_text(_yaml.safe_dump(minimal_manifest_dict), encoding="utf-8")
        with pytest.raises(ManifestLoadError):
            load_manifest(target)

    def test_missing_code_paths_rejected(self, write_manifest):
        with pytest.raises(ManifestLoadError):
            path = write_manifest(
                {"spec": {"subsystems": [
                    {
                        "id": "alpha",
                        "title": "Alpha",
                        "owner": "tim",
                        "lifecycle_stage": "adopt",
                        "code_paths": [],  # empty list → invalid
                    },
                ]}}
            )
            load_manifest(path)

    def test_unsupported_schema_version_rejected(self, write_manifest):
        with pytest.raises(ManifestLoadError, match="0.1.x"):
            path = write_manifest({"schema_version": "0.2.0"})
            load_manifest(path)


class TestCrossFieldValidation:
    def test_duplicate_subsystem_ids_rejected(self, write_manifest):
        with pytest.raises(ManifestLoadError, match="Duplicate subsystem"):
            path = write_manifest(
                {"spec": {"subsystems": [
                    {
                        "id": "alpha",
                        "title": "Alpha 1",
                        "owner": "tim",
                        "lifecycle_stage": "adopt",
                        "code_paths": ["src/a/**/*.py"],
                        "published_interfaces": {"python": ["a.x"]},
                    },
                    {
                        "id": "alpha",  # dup
                        "title": "Alpha 2",
                        "owner": "tim",
                        "lifecycle_stage": "adopt",
                        "code_paths": ["src/b/**/*.py"],
                        "allowed_outbound": [{"subsystem": "alpha"}],
                    },
                ]}}
            )
            load_manifest(path)

    def test_published_interfaces_required_when_inbound(self, write_manifest):
        """Per Atlas review: required only if depended-upon."""
        with pytest.raises(ManifestLoadError, match="published_interfaces"):
            path = write_manifest(
                {"spec": {"subsystems": [
                    {
                        "id": "alpha",
                        "title": "Alpha",
                        "owner": "tim",
                        "lifecycle_stage": "adopt",
                        "code_paths": ["src/alpha/**/*.py"],
                        # alpha has inbound (from beta) but NO published_interfaces
                    },
                    {
                        "id": "beta",
                        "title": "Beta",
                        "owner": "tim",
                        "lifecycle_stage": "adopt",
                        "code_paths": ["src/beta/**/*.py"],
                        "allowed_outbound": [{"subsystem": "alpha"}],
                    },
                ]}}
            )
            load_manifest(path)

    def test_published_interfaces_optional_when_no_inbound(self, write_manifest):
        """An internal-only leaf can omit published_interfaces."""
        path = write_manifest(
            {"spec": {"subsystems": [
                {
                    "id": "alpha",
                    "title": "Alpha",
                    "owner": "tim",
                    "lifecycle_stage": "adopt",
                    "code_paths": ["src/alpha/**/*.py"],
                    # no published_interfaces; no inbound edges either → OK
                },
                {
                    "id": "beta",
                    "title": "Beta",
                    "owner": "tim",
                    "lifecycle_stage": "adopt",
                    "code_paths": ["src/beta/**/*.py"],
                    "allowed_outbound": [{"external": "yaml"}],
                },
            ]}}
        )
        m = load_manifest(path)
        assert m.spec.subsystems[0].published_interfaces is None


class TestOutboundEdgeExclusivity:
    def test_external_and_subsystem_mutex(self, write_manifest):
        with pytest.raises(ManifestLoadError):
            path = write_manifest(
                {"spec": {"subsystems": [
                    {
                        "id": "alpha",
                        "title": "Alpha",
                        "owner": "tim",
                        "lifecycle_stage": "adopt",
                        "code_paths": ["src/alpha/**/*.py"],
                        "allowed_outbound": [
                            {"subsystem": "beta", "external": "yaml"},  # both set
                        ],
                    },
                ]}}
            )
            load_manifest(path)


class TestCatchAllBucket:
    def test_path_field_accepted(self, write_manifest):
        """Per Atlas review: catch_all_buckets uses `path:`, not `subsystem:`."""
        path = write_manifest(
            {"spec": {
                "catch_all_buckets": [
                    {
                        "path": "src/legacy/**/*.py",
                        "rationale": "Under retire",
                        "sunset_target": "2026-09-01",
                    }
                ]
            }}
        )
        m = load_manifest(path)
        assert len(m.spec.catch_all_buckets) == 1
        assert m.spec.catch_all_buckets[0].path == "src/legacy/**/*.py"
