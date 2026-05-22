"""Evidence emission per AD-2 (PANEL-SYNTHESIS-AND-DECISIONS-2026-05-22.md).

Each conformance check emits one evidence record to
`evidence/YYYY-MM-DD/eng-conformance.jsonl` (per JOS-D0063 append-only
evidence ledger convention).

Record schema (AD-2):
    {
        "check_id":      str,                # "structure-coverage" | "dependency-direction"
        "category":      "structure",
        "tool":          "foundry-eng-conformance@<version>",
        "result":        "pass" | "fail" | "skipped",
        "commit_sha":    str | null,         # null when not in a git repo
        "evidence_uri":  str,                # path back to this record
        "timestamp":     str,                # ISO-8601 UTC
        "details":       dict,               # check-specific structured details
    }

The gate (--mode=enforce) verifies one record exists per required check
and fails if any record has result="fail". --mode=report writes the
same record but never fails CI.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from foundry_eng_conformance import __version__


@dataclass
class EvidenceRecord:
    check_id: str
    result: str  # "pass" | "fail" | "skipped"
    details: dict = field(default_factory=dict)
    category: str = "structure"
    commit_sha: str | None = None
    timestamp: str | None = None
    tool: str = ""
    evidence_uri: str = ""

    def __post_init__(self):
        if not self.tool:
            self.tool = f"foundry-eng-conformance@{__version__}"
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "category": self.category,
            "tool": self.tool,
            "result": self.result,
            "commit_sha": self.commit_sha,
            "evidence_uri": self.evidence_uri,
            "timestamp": self.timestamp,
            "details": self.details,
        }


def _detect_commit_sha(repo_root: Path) -> str | None:
    """Best-effort `git rev-parse HEAD`. Returns None on any failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def evidence_dir(repo_root: Path, date: str | None = None) -> Path:
    """Path to the day's evidence directory (created on demand)."""
    date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return repo_root / "evidence" / date


def evidence_file(repo_root: Path, date: str | None = None) -> Path:
    """Path to the day's `eng-conformance.jsonl` evidence file."""
    return evidence_dir(repo_root, date) / "eng-conformance.jsonl"


def emit_records(
    records: list[EvidenceRecord], repo_root: str | Path
) -> Path:
    """Append the given records as JSONL to today's evidence file.

    Returns the evidence file path. Creates parent dirs as needed.
    Idempotent — each invocation appends; no deduplication.
    """
    repo_root = Path(repo_root).resolve()
    sha = _detect_commit_sha(repo_root)
    out_path = evidence_file(repo_root)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Find current line count so evidence_uri can point at the new line
    start_line = 0
    if out_path.exists():
        with out_path.open("rb") as f:
            start_line = sum(1 for _ in f)

    rel_path = out_path.relative_to(repo_root).as_posix()
    with out_path.open("a", encoding="utf-8") as f:
        for i, rec in enumerate(records):
            rec.commit_sha = sha
            line_no = start_line + i + 1
            rec.evidence_uri = f"{rel_path}#L{line_no}"
            f.write(json.dumps(rec.to_dict(), separators=(",", ":")) + "\n")

    return out_path
