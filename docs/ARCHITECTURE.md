# Architecture

The lab is organized around immutable artifacts and one promotion boundary.

1. `corpus.py` generates versioned fictional cases and evidence spans.
2. `evaluator.py` produces evidence-bound verdicts through local rules or a provider adapter.
3. `memory.py` retrieves only promoted training precedents and explains ranking components.
4. `benchmark.py` measures each failure mode, severity, abstention, agreement, and calibration.
5. `workflow.py` persists cases, verdicts, human decisions, promotions, and a hash-chained audit log.
6. `provenance.py` freezes run inputs, traces, replay identity, and evidence packets.
7. `api.py`, `ui.py`, and `cli.py` expose the same workflow state through HTTP, browser, and shell.

DuckDB is the durable local store. Pydantic contracts reject undeclared fields and invalid evidence.
SHA-256 identities make source, corpus, verdict, manifest, and report drift explicit.

The system is modular at provider boundaries: a production embedding or judge can implement the
existing protocol without taking ownership of evidence validation, split policy, audit, or replay.
