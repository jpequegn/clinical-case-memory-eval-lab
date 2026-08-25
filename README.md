# Clinical Case Memory Eval Lab

Clinical Case Memory Eval Lab is a privacy-safe engineering environment for evaluating generated
clinical notes against synthetic transcripts. It focuses on plausible omissions, unsupported
inferences, plan reversals, unsafe certainty, cited evidence, abstention, and regression detection.

Source project: [project-ideas #244](https://github.com/jpequegn/project-ideas/issues/244).

## Safety Boundary

This project uses generated fictional cases only. It is not medical advice, a clinical decision
support system, or a safety certification. Do not ingest protected health information, real patient
records, or production credentials.

## Development

```bash
uv sync --all-groups
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

The scenario corpus, evaluators, reviewed-case memory, calibration gates, review workflow, replay
manifests, and interface are tracked as repository issues.

Licensed under the MIT License.
