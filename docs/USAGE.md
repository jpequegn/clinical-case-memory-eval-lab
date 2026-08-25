# Usage

Generate and inspect the corpus:

```bash
uv run --no-sync case-memory-eval corpus --output fixtures/cases.json
uv run --no-sync case-memory-eval evaluate --index 1
```

Run the complete local demonstration and reviewer interface:

```bash
uv run --no-sync case-memory-eval demo --output demo-output
uv run --no-sync case-memory-eval serve \
  --database demo-output/clinical-case-memory.duckdb --port 4320
```

Operate the review workflow from the shell:

```bash
uv run --no-sync case-memory-eval ingest --database lab.duckdb --index 1
uv run --no-sync case-memory-eval review --database lab.duckdb
uv run --no-sync case-memory-eval review --database lab.duckdb \
  --result-id RESULT_ID --decision accepted --idempotency-key review-001
uv run --no-sync case-memory-eval promote --database lab.duckdb --review-id REVIEW_ID
```

Run and preserve evaluations:

```bash
uv run --no-sync case-memory-eval benchmark --mode static_rules --output benchmark.json
uv run --no-sync case-memory-eval replay --record demo-output/run.json \
  --database demo-output/clinical-case-memory.duckdb
uv run --no-sync case-memory-eval report --record demo-output/run.json \
  --output evidence.md --format markdown
```

Retrieval-grounded benchmark mode requires a database containing promoted training cases. `demo`
creates one. JSON output is canonical and suitable for scripts.
