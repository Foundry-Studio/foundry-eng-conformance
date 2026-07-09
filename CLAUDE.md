# CLAUDE.md - foundry-eng-conformance

## Scratch files (JOS-R20)

Write ephemeral output (SQL scratch, JSON/API dumps, LLM consult responses, debug logs) ONLY to `.scratchpad/` - it is gitignored. Never dump scratch files at the repo root or the current working directory. Scratchpad contents are purgeable after 30 days; promote anything worth keeping to a proper location first.
