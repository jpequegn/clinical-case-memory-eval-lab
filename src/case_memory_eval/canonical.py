"""Stable serialization and content identities."""

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Serialize JSON-compatible data with stable ordering and separators."""
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def content_id(value: Any) -> str:
    """Return a SHA-256 identity for JSON-compatible data."""
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()
