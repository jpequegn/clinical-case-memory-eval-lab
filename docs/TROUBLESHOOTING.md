# Troubleshooting

## The package does not import after sync

Use the documented non-editable install. Editable `.pth` handling can be unreliable when a workspace
path contains spaces.

```bash
uv sync --all-groups --no-editable
uv run --no-sync case-memory-eval version
```

After source edits, add `--reinstall-package clinical-case-memory-eval-lab` to the sync command so
the non-editable wheel is rebuilt.

## The browser test cannot launch Chromium

```bash
uv run --no-sync playwright install chromium
```

## Replay reports changed inputs

This is a fail-closed behavior. Use the listed provenance fields to restore the original corpus,
prompt/model, policy, and memory snapshot. Do not overwrite the historical run to make it compare.

## A review cannot be promoted

Only an `accepted` decision can be promoted. Rejected and deferred decisions remain non-influential.
Use a new idempotency key when recording materially different review content.

## The UI is unreachable

Confirm the server is bound to the expected local port and visit `http://127.0.0.1:4320`. If the port
is occupied, pass another value with `--port`.
