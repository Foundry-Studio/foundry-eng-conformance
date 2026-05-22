"""Tests for evidence emission (AD-2 contract)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from foundry_eng_conformance.evidence import (
    EvidenceRecord,
    emit_records,
    evidence_file,
)


class TestEvidenceRecord:
    def test_default_tool_string_includes_version(self):
        from foundry_eng_conformance import __version__

        rec = EvidenceRecord(check_id="x", result="pass")
        assert rec.tool == f"foundry-eng-conformance@{__version__}"

    def test_default_timestamp_is_utc_iso(self):
        rec = EvidenceRecord(check_id="x", result="pass")
        # Parses as ISO 8601 with Z suffix
        ts = rec.timestamp
        assert ts is not None and ts.endswith("Z")
        parsed = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        parsed = parsed.replace(tzinfo=timezone.utc)
        assert (datetime.now(timezone.utc) - parsed).total_seconds() < 60

    def test_to_dict_has_all_ad2_fields(self):
        rec = EvidenceRecord(check_id="structure-coverage", result="pass", details={"x": 1})
        d = rec.to_dict()
        required = {
            "check_id", "category", "tool", "result", "commit_sha",
            "evidence_uri", "timestamp", "details",
        }
        assert set(d.keys()) == required


class TestEmitRecords:
    def test_writes_jsonl_to_dated_path(self, tmp_path):
        rec = EvidenceRecord(check_id="x", result="pass", details={"n": 0})
        out = emit_records([rec], tmp_path)
        assert out.parent.name  # YYYY-MM-DD
        assert out.name == "eng-conformance.jsonl"
        # File is JSONL — one record per line
        lines = out.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["check_id"] == "x"
        assert parsed["result"] == "pass"

    def test_appends_on_repeat_calls(self, tmp_path):
        emit_records([EvidenceRecord(check_id="a", result="pass")], tmp_path)
        emit_records([EvidenceRecord(check_id="b", result="fail")], tmp_path)
        out = evidence_file(tmp_path)
        lines = out.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["check_id"] == "a"
        assert json.loads(lines[1])["check_id"] == "b"

    def test_evidence_uri_points_at_correct_line(self, tmp_path):
        emit_records([EvidenceRecord(check_id="a", result="pass")], tmp_path)
        emit_records([EvidenceRecord(check_id="b", result="fail")], tmp_path)
        out = evidence_file(tmp_path)
        lines = out.read_text(encoding="utf-8").splitlines()
        rec_a = json.loads(lines[0])
        rec_b = json.loads(lines[1])
        assert rec_a["evidence_uri"].endswith("#L1")
        assert rec_b["evidence_uri"].endswith("#L2")

    def test_multiple_records_in_one_call(self, tmp_path):
        recs = [
            EvidenceRecord(check_id="structure-coverage", result="pass"),
            EvidenceRecord(check_id="dependency-direction", result="fail"),
        ]
        out = emit_records(recs, tmp_path)
        lines = out.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        # Both records reference the same file but different lines
        rec0 = json.loads(lines[0])
        rec1 = json.loads(lines[1])
        assert rec0["evidence_uri"].endswith("#L1")
        assert rec1["evidence_uri"].endswith("#L2")
