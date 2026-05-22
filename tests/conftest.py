"""Shared pytest fixtures.

Most tests need: (a) a minimal valid manifest dict for tweaking, and
(b) a tmp_path repo with code laid out per a given manifest.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


MINIMAL_MANIFEST: dict = {
    "schema_version": "0.1.0",
    "apiVersion": "foundry.studio/v1",
    "kind": "EngManifest",
    "metadata": {
        "name": "test-repo",
        "uuid": "11111111-2222-3333-4444-555555555555",
        "owner": "tim",
        "repo_kind": "monorepo",
    },
    "spec": {
        "reproducible_build": {"declared": True, "source_of_truth": "pyproject.toml"},
        "ownership_source": {"file": "CODEOWNERS"},
        "subsystems": [
            {
                "id": "alpha",
                "title": "Alpha subsystem",
                "owner": "tim",
                "lifecycle_stage": "adopt",
                "code_paths": ["src/alpha/**/*.py"],
                "allowed_outbound": [
                    {"external": "yaml"},
                ],
                "published_interfaces": {"python": ["alpha.service"]},
            },
            {
                "id": "beta",
                "title": "Beta subsystem",
                "owner": "tim",
                "lifecycle_stage": "adopt",
                "code_paths": ["src/beta/**/*.py"],
                "allowed_outbound": [
                    {"subsystem": "alpha", "why": "calls Alpha API"},
                ],
            },
        ],
    },
}


@pytest.fixture
def minimal_manifest_dict() -> dict:
    """Returns a fresh deep copy each call so tests can mutate freely."""
    import copy

    return copy.deepcopy(MINIMAL_MANIFEST)


@pytest.fixture
def write_manifest(tmp_path: Path, minimal_manifest_dict: dict):
    """Factory that writes a manifest to <tmp_path>/.foundry/eng-manifest.yaml."""

    def _write(overrides: dict | None = None) -> Path:
        data = minimal_manifest_dict
        if overrides:
            _deep_merge(data, overrides)
        target = tmp_path / ".foundry" / "eng-manifest.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(yaml.safe_dump(data), encoding="utf-8")
        return target

    return _write


def _deep_merge(dest: dict, src: dict) -> None:
    """Mutate dest by merging src into it (lists are replaced, not merged)."""
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dest.get(k), dict):
            _deep_merge(dest[k], v)
        else:
            dest[k] = v
