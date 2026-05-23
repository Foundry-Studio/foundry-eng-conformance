"""foundry-eng-conformance — JOS-S53 architecture-conformance checks.

Implements the two checks JOS-S53 requires:
  1. Structure coverage — every code unit maps to exactly one declared
     subsystem (no catch-all bucket).
  2. Dependency direction + acyclic — actual import graph respects the
     manifest's allowed_outbound declarations and JOS-P20 (no cycles).

Consumes `.foundry/eng-manifest.yaml` in the target repo. See SCHEMA.md
for the manifest contract.
"""

__version__ = "0.1.1"
__schema_version__ = "0.1.1"
