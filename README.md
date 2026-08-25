# Clinical Case Memory Eval Lab

Clinical Case Memory Eval Lab evaluates generated clinical notes against fictional transcripts. It
detects omissions, unsupported inferences, plan reversals, and unsafe certainty; attaches exact
source evidence; retrieves reviewed precedents without holdout leakage; and gates regressions by
failure class and severity.

Source project: [project-ideas #244](https://github.com/jpequegn/project-ideas/issues/244).

## Safety Boundary

This repository is an evaluation engineering lab. It is not medical advice, a clinical decision
support system, a medical device, or a safety certification. The included data is deterministic and
fictional. Do not ingest protected health information, unredacted patient records, or production
credentials.

## Quick Start

Python 3.12 and [uv](https://docs.astral.sh/uv/) are required.

```bash
uv sync --all-groups --no-editable
uv run --no-sync playwright install chromium
uv run --no-sync case-memory-eval demo --output demo-output
uv run --no-sync case-memory-eval serve \
  --database demo-output/clinical-case-memory.duckdb --port 4320
```

Open [http://127.0.0.1:4320](http://127.0.0.1:4320) to inspect the queued synthetic case, compare
the transcript and note, review cited findings, and accept/promote, reject, or defer it.

## Capabilities

- A content-addressed, balanced 36-case synthetic golden corpus.
- Evidence-first local rules plus a provider-neutral structured judge contract with abstention.
- DuckDB reviewed-case memory with deterministic embeddings and explainable score components.
- Per-class confusion metrics, severe recall, calibration error, and configurable regression gates.
- An audited FastAPI review workflow with idempotency and accepted-only promotion.
- Immutable run manifests, drift-aware replay, correlated traces, and evidence packets.
- CLI and browser workflows that require no API keys.

Run `uv run --no-sync case-memory-eval --help` for all commands. See [usage](docs/USAGE.md),
[methodology](docs/METHODOLOGY.md), [architecture](docs/ARCHITECTURE.md), and the
[project guide](docs/PROJECT_GUIDE.md).

## Development And Release

```bash
uv run --no-sync ruff format --check .
uv run --no-sync ruff check .
uv run --no-sync mypy
uv run --no-sync pytest
uv run --no-sync case-memory-release-check
```

The release command validates formatting, lint, typing, tests, the deterministic demo, wheel/sdist
builds, and required package contents. Licensed under the MIT License.

After changing package source in a workspace path containing spaces, refresh the non-editable local
wheel with `uv sync --all-groups --no-editable --reinstall-package clinical-case-memory-eval-lab`
before running commands outside pytest.
